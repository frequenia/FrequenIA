"""Integração opt-in Fase 27: PostgreSQL, S3 compatível e ClamAV reais."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import test_phase25_postgres_integration as phase25
from flask import Flask
from routes.occurrences import occurrences_bp
from routes.timekeeping import timekeeping_bp
from services.attachment_purge import purge_expired
from services.attachment_scanner import ClamAVScanner, FakeScanner, ScanResult
from services.correction_attachment_storage import LocalPrivateAttachmentStorage, S3PrivateAttachmentStorage
from services.correction_attachment_storage import AttachmentStorageError

URL=os.environ.get("PHASE27_TEST_DATABASE_URL","").strip()
def _safe_test_url():
    if not URL:
        return False
    parsed=urlparse(URL)
    if parsed.scheme not in {"postgres","postgresql"}:
        raise RuntimeError("PHASE27_TEST_DATABASE_URL deve apontar para PostgreSQL.")
    allowed_hosts={"localhost","127.0.0.1","::1"}
    disposable_host=os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST","").strip()
    if disposable_host: allowed_hosts.add(disposable_host)
    if parsed.hostname not in allowed_hosts:
        raise RuntimeError("A integração da Fase 27 aceita somente PostgreSQL local.")
    if parsed.path != "/frequenia_phase25_test":
        raise RuntimeError("O database descartável deve se chamar frequenia_phase25_test.")
    return True

ENABLED=_safe_test_url()
if ENABLED:
    phase25.TEST_DATABASE_URL=URL
    phase25.POSTGRES_ENABLED=True

PDF=b"%PDF-1.4\nclean fixture\n%%EOF\n"
EICAR_MARKER=b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
EICAR=(b"%PDF-1.4\n1 0 obj\n<< /Length 68 >>\nstream\n"+EICAR_MARKER+
       b"\nendstream\nendobj\n%%EOF\n")

@unittest.skipUnless(ENABLED,"requer PHASE27_TEST_DATABASE_URL explícita")
class Phase27PostgresIntegrationTests(unittest.TestCase):
    for _name in ("COMPANY","UNIT","TEAM","OTHER_TEAM","FOREIGN_COMPANY","FOREIGN_UNIT","FOREIGN_TEAM","EMPLOYEE_USER","EMPLOYEE","OTHER_USER","OTHER_EMPLOYEE","MANAGER_USER","MANAGER","HR_USER","HR","ADMIN_USER","ADMIN","FOREIGN_USER","FOREIGN_EMPLOYEE","FOREIGN_HR_USER","FOREIGN_HR","FOREIGN_ADMIN_USER","FOREIGN_ADMIN","MARKING","EXIT_MARKING","OTHER_MARKING","FOREIGN_MARKING"):
        locals()[_name]=getattr(phase25.Phase25PostgresIntegrationTests,_name)
    del _name
    _seed=phase25.Phase25PostgresIntegrationTests._seed
    _auth=phase25.Phase25PostgresIntegrationTests._auth
    _database_patches=phase25.Phase25PostgresIntegrationTests._database_patches
    _request=phase25.Phase25PostgresIntegrationTests._request
    _create=phase25.Phase25PostgresIntegrationTests._create
    _decide=phase25.Phase25PostgresIntegrationTests._decide
    _effective=phase25.Phase25PostgresIntegrationTests._effective

    @classmethod
    def setUpClass(cls):
        phase25._reset_database(); phase25._apply_migrations(1,21)
        fixture=cls(methodName="runTest"); connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                fixture._seed(cursor)
                cursor.execute("""INSERT INTO correcoes(empresa_id,funcionario_id,solicitante_usuario_id,tipo,categoria,motivo,estado)
                                  VALUES(%s,%s,%s,'justificativa','justificativa','upgrade 022','pendente_gestor') RETURNING id""",
                               (cls.COMPANY,cls.EMPLOYEE,cls.EMPLOYEE_USER)); correction_id=cursor.fetchone()["id"]
                cursor.execute("""INSERT INTO anexos_correcao(empresa_id,correcao_id,funcionario_id,enviado_por_usuario_id,
                                  chave_objeto,nome_original,tipo_mime,tamanho_bytes,sha256)
                                  VALUES(%s,%s,%s,%s,%s,'legacy.pdf','application/pdf',12,%s) RETURNING id""",
                               (cls.COMPANY,correction_id,cls.EMPLOYEE,cls.EMPLOYEE_USER,
                                "correcoes/00000000-0000-0000-0000-000000000027.pdf","0"*64)); attachment_id=cursor.fetchone()["id"]
            connection.commit()
        finally: connection.close()
        phase25._apply_migrations(22,22)
        connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT estado,estado_seguranca,scan_resultado_codigo FROM anexos_correcao WHERE id=%s",(attachment_id,)); cls.upgrade_evidence=cursor.fetchone()
        finally: connection.close()
        phase25._reset_database(); phase25._apply_migrations(1,22)
        cls.app=Flask("phase27"); cls.app.config.update(TESTING=True,SECRET_KEY="phase27-test")
        cls.app.register_blueprint(occurrences_bp); cls.app.register_blueprint(timekeeping_bp)

    def setUp(self):
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor: cursor.execute("TRUNCATE empresas,usuarios CASCADE"); self._seed(cursor)
            connection.commit()
        finally: connection.close()
        self.temp=tempfile.TemporaryDirectory(prefix="frequenia-phase27-")
        self.env=patch.dict(os.environ,{"APP_ENV":"test","ATTACHMENT_STORAGE_PROVIDER":"local","ATTACHMENT_STORAGE_ROOT":self.temp.name,"ATTACHMENT_SCANNER_PROVIDER":"fake-clean","ATTACHMENT_SCAN_MODE":"sync"}); self.env.start()

    def tearDown(self): self.env.stop(); self.temp.cleanup()
    def _upload(self,cid,content=PDF):
        return self._request(self._auth("funcionario"),"PUT",f"/api/ocorrencias/{cid}/comprovante",data={"comprovante":(BytesIO(content),"proof.pdf","application/pdf")},content_type="multipart/form-data")
    def _row(self,cid):
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur: cur.execute("SELECT * FROM anexos_correcao WHERE correcao_id=%s ORDER BY created_at DESC LIMIT 1",(cid,)); return cur.fetchone()
        finally: c.close()

    def test_00_migration_022_clean_install_and_021_upgrade(self):
        self.assertEqual(self.upgrade_evidence["estado"],"ativo")
        self.assertEqual(self.upgrade_evidence["estado_seguranca"],"limpo")
        self.assertEqual(self.upgrade_evidence["scan_resultado_codigo"],"migrado_fase26")
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT conname FROM pg_constraint WHERE conrelid='anexos_correcao'::regclass
                               AND conname IN ('anexos_correcao_seguranca_check','anexos_correcao_purgado_check')""")
                self.assertEqual(len(cur.fetchall()),2)
        finally: c.close()

    def test_01_clean_quarantine_scan_and_download_gate(self):
        cid=self._create()
        observed=[]
        class UnknownScanner:
            def scan(inner,content):
                observed.append(self._row(cid)["estado_seguranca"])
                return ScanResult("desconhecido","unknown")
        with patch("services.correction_attachments.get_attachment_scanner",return_value=UnknownScanner()):
            response=self._upload(cid)
        self.assertEqual(observed,["quarentena"])
        self.assertEqual(response.get_json()["estado_seguranca"],"erro_varredura")
        blocked=self._request(self._auth("funcionario"),"GET",f"/api/ocorrencias/{cid}/comprovante/download")
        self.assertEqual(blocked.status_code,423); self.assertEqual(blocked.data.count(PDF),0)
        with patch("services.correction_attachments.get_attachment_scanner",return_value=FakeScanner("limpo")):
            retry=self._request(self._auth("gestor"),"POST",f"/api/gestao/ocorrencias/{cid}/comprovante/retry-scan")
        self.assertEqual(retry.get_json()["estado_seguranca"],"limpo")
        self.assertEqual(self._request(self._auth("funcionario"),"GET",f"/api/ocorrencias/{cid}/comprovante/download").data,PDF)
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) total FROM anexos_correcao WHERE correcao_id=%s",(cid,)); self.assertEqual(cur.fetchone()["total"],1)
                cur.execute("SELECT count(*) total FROM auditoria WHERE entidade_id=%s AND acao='correcao.anexo_varredura_retry'",(cid,)); self.assertEqual(cur.fetchone()["total"],1)
        finally: c.close()

    def test_02_real_clamav_eicar_is_infected_and_never_downloaded(self):
        host=os.environ.get("PHASE27_CLAMAV_HOST")
        if not host: self.fail("PHASE27_CLAMAV_HOST é obrigatório quando a suíte está habilitada")
        cid=self._create()
        with patch("services.correction_attachments.get_attachment_scanner",return_value=ClamAVScanner(host,int(os.getenv("PHASE27_CLAMAV_PORT","3310")),20)):
            response=self._upload(cid,EICAR)
        self.assertEqual(response.get_json()["estado_seguranca"],"infectado")
        self.assertIsNotNone(self._row(cid)["retencao_ate"])
        denied=self._request(self._auth("funcionario"),"GET",f"/api/ocorrencias/{cid}/comprovante/download")
        self.assertEqual(denied.status_code,423); self.assertNotIn(b"EICAR",denied.data)

    def test_03_substitution_removal_and_active_retention_policy(self):
        cid=self._create(); self._upload(cid); self._upload(cid)
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT estado,retencao_ate FROM anexos_correcao WHERE correcao_id=%s ORDER BY created_at",(cid,)); rows=cur.fetchall()
        finally: c.close()
        self.assertEqual(rows[0]["estado"],"substituido"); self.assertIsNotNone(rows[0]["retencao_ate"]); self.assertIsNone(rows[1]["retencao_ate"])
        self._request(self._auth("funcionario"),"DELETE",f"/api/ocorrencias/{cid}/comprovante")
        self.assertIsNotNone(self._row(cid)["retencao_ate"])

    def test_04_purge_dry_run_expiry_failure_idempotency_batch_and_history(self):
        ids=[]
        for _ in range(2):
            cid=self._create(); self._upload(cid); self._request(self._auth("funcionario"),"DELETE",f"/api/ocorrencias/{cid}/comprovante"); ids.append(cid)
        active_id=self._create(); self._upload(active_id)
        storage=LocalPrivateAttachmentStorage(self.temp.name)
        self.assertEqual(purge_expired(phase25._connect,storage=storage,execute=True)["candidatos"],0)
        c=phase25._connect()
        try:
            with c.cursor() as cur: cur.execute("UPDATE anexos_correcao SET retencao_ate=clock_timestamp()-interval '1 day'")
            c.commit()
        finally: c.close()
        self.assertEqual(purge_expired(phase25._connect,storage=storage,batch_size=1)["purgados"],0)
        first=purge_expired(phase25._connect,storage=storage,execute=True,batch_size=1); second=purge_expired(phase25._connect,storage=storage,execute=True,batch_size=10); third=purge_expired(phase25._connect,storage=storage,execute=True)
        self.assertEqual((first["purgados"],second["purgados"],third["purgados"]),(1,1,0))
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT count(*) total FROM anexos_correcao WHERE purgado_at IS NOT NULL"); self.assertEqual(cur.fetchone()["total"],2)
                cur.execute("SELECT purgado_at FROM anexos_correcao WHERE correcao_id=%s AND estado='ativo'",(active_id,)); self.assertIsNone(cur.fetchone()["purgado_at"])
        finally: c.close()

    def test_05_purge_failure_is_retryable_and_audited_without_key(self):
        cid=self._create(); self._upload(cid); self._request(self._auth("funcionario"),"DELETE",f"/api/ocorrencias/{cid}/comprovante")
        c=phase25._connect()
        try:
            with c.cursor() as cur: cur.execute("UPDATE anexos_correcao SET retencao_ate=clock_timestamp()-interval '1 day'")
            c.commit()
        finally: c.close()
        class FailingStorage:
            def delete(self,key): raise AttachmentStorageError("indisponível")
        result=purge_expired(phase25._connect,storage=FailingStorage(),execute=True)
        self.assertEqual(result["falhas"],1)
        c=phase25._connect(dict_rows=True)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT purgado_at,purge_tentativas,purge_erro_codigo,chave_objeto FROM anexos_correcao LIMIT 1"); row=cur.fetchone()
                self.assertIsNone(row["purgado_at"]); self.assertEqual(row["purge_tentativas"],1); self.assertEqual(row["purge_erro_codigo"],"storage_unavailable")
                cur.execute("SELECT acao,metadados::text AS metadata FROM auditoria WHERE acao LIKE 'correcao.anexo_purge_%' ORDER BY ocorrido_at")
                audit=cur.fetchall(); self.assertEqual([item["acao"] for item in audit],["correcao.anexo_purge_inicio","correcao.anexo_purge_falha"])
                self.assertNotIn(row["chave_objeto"]," ".join(item["metadata"] for item in audit))
        finally: c.close()

    def test_06_concurrent_purge_processes_one_record_once(self):
        cid=self._create(); self._upload(cid); self._request(self._auth("funcionario"),"DELETE",f"/api/ocorrencias/{cid}/comprovante")
        c=phase25._connect()
        try:
            with c.cursor() as cur: cur.execute("UPDATE anexos_correcao SET retencao_ate=clock_timestamp()-interval '1 day'")
            c.commit()
        finally: c.close()
        base=LocalPrivateAttachmentStorage(self.temp.name)
        class CountingStorage:
            def __init__(self): self.count=0; self.lock=threading.Lock()
            def delete(inner,key):
                with inner.lock: inner.count+=1
                base.delete(key)
        storage=CountingStorage()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:purge_expired(phase25._connect,storage=storage,execute=True),range(2)))
        self.assertEqual(sum(item["purgados"] for item in results),1); self.assertEqual(storage.count,1)

    def test_07_s3_compatible_service_round_trip(self):
        endpoint=os.environ.get("PHASE27_S3_ENDPOINT_URL")
        if not endpoint: self.fail("PHASE27_S3_ENDPOINT_URL é obrigatório quando a suíte está habilitada")
        import boto3
        client=boto3.client("s3",endpoint_url=endpoint,region_name="us-east-1",aws_access_key_id="phase27",aws_secret_access_key="phase27-local-only")
        bucket="frequenia-phase27-test";
        try: client.create_bucket(Bucket=bucket)
        except client.exceptions.BucketAlreadyOwnedByYou: pass
        storage=S3PrivateAttachmentStorage(bucket,"us-east-1",endpoint,client=client); key=storage.generate_key("pdf",self.COMPANY); storage.put(key,PDF,"application/pdf",__import__('hashlib').sha256(PDF).hexdigest())
        self.assertEqual(storage.read(key,len(PDF),__import__('hashlib').sha256(PDF).hexdigest()),PDF); storage.delete(key)

if __name__=="__main__": unittest.main()
