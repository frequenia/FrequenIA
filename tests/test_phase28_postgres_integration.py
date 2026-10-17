"""Integração opt-in da Fase 28 com PostgreSQL e fila determinística."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse,urlunparse

import psycopg2
import psycopg2.extras
import test_phase25_postgres_integration as phase25
from flask import Flask

from routes.occurrences import occurrences_bp
from services.attachment_outbox import dispatch_pending
from services.attachment_queue import InMemoryAttachmentQueue,QueueMessage,SQSAttachmentQueue,build_scan_payload
from services.attachment_reconciliation import reconcile_attachments
from services.attachment_scanner import FakeScanner
from services.attachment_worker import process_message
from services.correction_attachment_storage import LocalPrivateAttachmentStorage


URL=os.environ.get("PHASE28_TEST_DATABASE_URL","").strip()
def _safe_url():
    if not URL: return False
    parsed=urlparse(URL)
    allowed_hosts={"localhost","127.0.0.1","::1"}
    disposable_host=os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST","").strip()
    if disposable_host: allowed_hosts.add(disposable_host)
    if parsed.scheme not in {"postgres","postgresql"} or parsed.hostname not in allowed_hosts or parsed.path!="/frequenia_phase25_test":
        raise RuntimeError("PHASE28_TEST_DATABASE_URL deve usar o banco local descartável frequenia_phase25_test.")
    return True
ENABLED=_safe_url()
if ENABLED:
    phase25.TEST_DATABASE_URL=URL; phase25.POSTGRES_ENABLED=True

PDF=b"%PDF-1.4\nphase28 clean\n%%EOF\n"


@unittest.skipUnless(ENABLED,"requer PHASE28_TEST_DATABASE_URL explícita")
class Phase28PostgresIntegrationTests(unittest.TestCase):
    for _name in ("COMPANY","UNIT","TEAM","OTHER_TEAM","FOREIGN_COMPANY","FOREIGN_UNIT","FOREIGN_TEAM","EMPLOYEE_USER","EMPLOYEE","OTHER_USER","OTHER_EMPLOYEE","MANAGER_USER","MANAGER","HR_USER","HR","ADMIN_USER","ADMIN","FOREIGN_USER","FOREIGN_EMPLOYEE","FOREIGN_HR_USER","FOREIGN_HR","FOREIGN_ADMIN_USER","FOREIGN_ADMIN","MARKING","EXIT_MARKING","OTHER_MARKING","FOREIGN_MARKING"):
        locals()[_name]=getattr(phase25.Phase25PostgresIntegrationTests,_name)
    del _name
    _seed=phase25.Phase25PostgresIntegrationTests._seed
    _auth=phase25.Phase25PostgresIntegrationTests._auth
    _database_patches=phase25.Phase25PostgresIntegrationTests._database_patches
    _request=phase25.Phase25PostgresIntegrationTests._request
    _create=phase25.Phase25PostgresIntegrationTests._create

    @classmethod
    def setUpClass(cls):
        phase25._reset_database(); phase25._apply_migrations(1,23)
        cls.app=Flask("phase28"); cls.app.config.update(TESTING=True,SECRET_KEY="phase28-test")
        cls.app.register_blueprint(occurrences_bp)

    def setUp(self):
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor: cursor.execute("TRUNCATE empresas,usuarios CASCADE"); self._seed(cursor)
            connection.commit()
        finally: connection.close()
        self.temp=tempfile.TemporaryDirectory(prefix="frequenia-phase28-")
        self.env=patch.dict(os.environ,{"APP_ENV":"test","ATTACHMENT_STORAGE_PROVIDER":"local","ATTACHMENT_STORAGE_ROOT":self.temp.name,"ATTACHMENT_SCANNER_PROVIDER":"fake-clean","ATTACHMENT_SCAN_MODE":"async","ATTACHMENT_QUEUE_PROVIDER":"memory","ATTACHMENT_QUEUE_VISIBILITY_SECONDS":"60"}); self.env.start()
        self.storage=LocalPrivateAttachmentStorage(self.temp.name)

    def tearDown(self): self.env.stop(); self.temp.cleanup()
    def _upload(self,cid):
        return self._request(self._auth("funcionario"),"PUT",f"/api/ocorrencias/{cid}/comprovante",data={"comprovante":(BytesIO(PDF),"proof.pdf","application/pdf")},content_type="multipart/form-data")
    def _rows(self,cid):
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT a.*,j.id job_id,j.estado job_estado FROM anexos_correcao a
                               LEFT JOIN anexo_varredura_jobs j ON j.anexo_id=a.id
                               WHERE a.correcao_id=%s ORDER BY a.created_at DESC""",(cid,)); return cur.fetchall()
        finally: c.close()

    def test_00_migration_and_upload_outbox_are_atomic_and_quarantined(self):
        cid=self._create(); response=self._upload(cid)
        self.assertEqual(response.status_code,200); self.assertEqual(response.get_json()["estado_seguranca"],"quarentena")
        rows=self._rows(cid); self.assertEqual(len(rows),1); self.assertEqual(rows[0]["job_estado"],"pendente_publicacao")
        self.assertEqual(rows[0]["scan_tentativas"],0)

    def test_01_rollback_leaves_no_attachment_job_or_object(self):
        cid=self._create()
        with patch("services.correction_attachments.create_scan_job",side_effect=RuntimeError("controlled")):
            with self.assertRaises(RuntimeError): self._upload(cid)
        self.assertEqual(self._rows(cid),[])
        self.assertEqual(list(Path(self.temp.name).rglob("*.pdf")),[])

    def test_02_dispatch_after_commit_retry_and_two_dispatchers(self):
        ids=[self._create(),self._create()]
        for cid in ids: self._upload(cid)
        queue=InMemoryAttachmentQueue()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:dispatch_pending(phase25._connect,queue=queue,batch_size=10),range(2)))
        self.assertEqual(sum(item["published"] for item in results),2)
        self.assertEqual(queue.stats()["visible"],2)
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) total,count(DISTINCT anexo_id) distinct_total FROM anexo_varredura_jobs")
                row=cur.fetchone(); self.assertEqual((row["total"],row["distinct_total"]),(2,2))
        finally: c.close()

    def test_03_worker_clean_duplicate_out_of_order_and_commit_before_ack(self):
        cid=self._create(); self._upload(cid); queue=InMemoryAttachmentQueue(); dispatch_pending(phase25._connect,queue=queue)
        message=queue.receive()[0]
        result=process_message(phase25._connect,queue,message,storage=self.storage,scanner=FakeScanner("limpo"))
        self.assertTrue(result.acknowledge); queue.delete(message.receipt_handle)
        row=self._rows(cid)[0]; self.assertEqual((row["estado_seguranca"],row["job_estado"]),("limpo","concluido"))
        duplicate=QueueMessage(message.body,"duplicate",message.message_id,2)
        self.assertEqual(process_message(phase25._connect,queue,duplicate,storage=self.storage,scanner=FakeScanner("limpo")).outcome,"duplicate_terminal")
        connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT acao,metadados::text metadata
                       FROM auditoria
                       WHERE entidade_tipo='anexo_varredura_job' AND entidade_id=%s""",
                    (row["job_id"],),
                )
                audits=cursor.fetchall()
        finally: connection.close()
        actions={audit["acao"] for audit in audits}
        self.assertTrue({
            "correcao.anexo_job_publicado",
            "correcao.anexo_job_consumo",
            "correcao.anexo_job_concluido",
        }.issubset(actions))
        serialized=" ".join(audit["metadata"] for audit in audits).lower()
        for forbidden in ("chave_objeto","bucket","proof.pdf","%pdf"):
            self.assertNotIn(forbidden,serialized)

    def test_04_infected_is_terminal_transient_is_not_acknowledged(self):
        infected=self._create(); self._upload(infected); q1=InMemoryAttachmentQueue(); dispatch_pending(phase25._connect,queue=q1)
        msg=q1.receive()[0]; result=process_message(phase25._connect,q1,msg,storage=self.storage,scanner=FakeScanner("infectado"))
        self.assertTrue(result.acknowledge); self.assertEqual(self._rows(infected)[0]["estado_seguranca"],"infectado")
        failed=self._create(); self._upload(failed); q2=InMemoryAttachmentQueue(); dispatch_pending(phase25._connect,queue=q2)
        msg2=q2.receive()[0]; result2=process_message(phase25._connect,q2,msg2,storage=self.storage,scanner=FakeScanner("erro"))
        self.assertFalse(result2.acknowledge); self.assertEqual(self._rows(failed)[0]["job_estado"],"falha_reprocessavel")

    def test_05_concurrent_duplicate_delivery_scans_once(self):
        cid=self._create(); self._upload(cid); row=self._rows(cid)[0]
        body=build_scan_payload(row["job_id"],row["id"],row["empresa_id"]); queue=InMemoryAttachmentQueue(); queue.send(body); queue.send(body); count={"value":0}; lock=threading.Lock()
        class CountingScanner(FakeScanner):
            def scan(inner,content):
                with lock: count["value"]+=1
                return super().scan(content)
        messages=queue.receive(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda message:process_message(phase25._connect,queue,message,storage=self.storage,scanner=CountingScanner("limpo")),messages))
        self.assertEqual(count["value"],1); self.assertEqual(self._rows(cid)[0]["job_estado"],"concluido")

    def test_06_reconciliation_dry_run_and_explicit_repair(self):
        cid=self._create(); self._upload(cid); row=self._rows(cid)[0]; self.storage.delete(row["chave_objeto"])
        report=reconcile_attachments(phase25._connect,storage=self.storage,company_id=self.COMPANY)
        self.assertEqual(report["counts"]["metadata_without_object"],1); self.assertTrue(report["dry_run"])
        with self.assertRaises(ValueError): reconcile_attachments(phase25._connect,storage=self.storage,company_id=self.COMPANY,repair="requeue-missing-job")

    def test_07_disposable_database_snapshot_restore_preserves_security_state(self):
        clean=self._create(); self._upload(clean); queue=InMemoryAttachmentQueue(); dispatch_pending(phase25._connect,queue=queue)
        message=queue.receive()[0]; process_message(phase25._connect,queue,message,storage=self.storage,scanner=FakeScanner("limpo"))
        quarantined=self._create(); self._upload(quarantined)
        parsed=urlparse(URL); admin=urlunparse(parsed._replace(path="/postgres")); restore_name="frequenia_phase28_restore_test"
        admin_connection=psycopg2.connect(admin); admin_connection.autocommit=True
        copied=tempfile.mkdtemp(prefix="frequenia-phase28-restore-")
        try:
            with admin_connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE IF EXISTS {restore_name}')
                cursor.execute(f'CREATE DATABASE {restore_name} TEMPLATE frequenia_phase25_test')
            shutil.copytree(self.temp.name,copied,dirs_exist_ok=True)
            restored_url=urlunparse(parsed._replace(path="/"+restore_name)); restored=psycopg2.connect(restored_url,cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                with restored.cursor() as cursor:
                    cursor.execute("SELECT estado_seguranca,chave_objeto,tamanho_bytes,sha256 FROM anexos_correcao ORDER BY created_at")
                    rows=cursor.fetchall(); self.assertEqual({row["estado_seguranca"] for row in rows},{"limpo","quarentena"})
                    clean_row=next(row for row in rows if row["estado_seguranca"]=="limpo")
                    self.assertEqual(LocalPrivateAttachmentStorage(copied).read(clean_row["chave_objeto"],clean_row["tamanho_bytes"],clean_row["sha256"]),PDF)
                    cursor.execute("SELECT count(*) total FROM anexo_varredura_jobs WHERE estado='pendente_publicacao'")
                    self.assertGreaterEqual(cursor.fetchone()["total"],1)
            finally: restored.close()
        finally:
            shutil.rmtree(copied,ignore_errors=True)
            with admin_connection.cursor() as cursor: cursor.execute(f'DROP DATABASE IF EXISTS {restore_name}')
            admin_connection.close()

    def test_08_disposable_sqs_round_trip_and_redrive_configuration(self):
        endpoint=os.getenv("PHASE28_SQS_ENDPOINT_URL")
        if not endpoint: self.fail("PHASE28_SQS_ENDPOINT_URL é obrigatório quando a suíte está habilitada")
        import boto3
        client=boto3.client("sqs",endpoint_url=endpoint,region_name="us-east-1")
        dlq_url=client.create_queue(QueueName="frequenia-phase28-dlq-test",Attributes={"SqsManagedSseEnabled":"true"})["QueueUrl"]
        dlq_arn=client.get_queue_attributes(QueueUrl=dlq_url,AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        queue_url=client.create_queue(QueueName="frequenia-phase28-main-test",Attributes={
            "SqsManagedSseEnabled":"true","ReceiveMessageWaitTimeSeconds":"1","VisibilityTimeout":"60",
            "RedrivePolicy":__import__('json').dumps({"deadLetterTargetArn":dlq_arn,"maxReceiveCount":"3"}),
        })["QueueUrl"]
        adapter=SQSAttachmentQueue(queue_url,"us-east-1",endpoint,client=client)
        body=build_scan_payload(self.COMPANY,self.EMPLOYEE,self.UNIT); adapter.send(body)
        messages=adapter.receive(1,1); self.assertEqual(len(messages),1); adapter.delete(messages[0].receipt_handle)
        attrs=client.get_queue_attributes(QueueUrl=queue_url,AttributeNames=["RedrivePolicy","SqsManagedSseEnabled"])["Attributes"]
        self.assertEqual(attrs["SqsManagedSseEnabled"],"true"); self.assertIn(dlq_arn,attrs["RedrivePolicy"])


if __name__=="__main__": unittest.main()
