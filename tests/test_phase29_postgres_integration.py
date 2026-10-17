"""Integração opt-in da Fase 29 com PostgreSQL real e recursos descartáveis."""
from concurrent.futures import ThreadPoolExecutor
import os,tempfile,unittest
from unittest.mock import patch
from urllib.parse import urlparse,urlunparse

import psycopg2
from flask import Flask
import test_phase25_postgres_integration as phase25
import test_phase28_postgres_integration as phase28

from routes.occurrences import occurrences_bp
from services.attachment_queue import InMemoryAttachmentQueue,QueueMessage,build_scan_payload
from services.controlled_redrive import RedriveError,redrive_messages
from services.correction_attachment_storage import AttachmentStorageError,LocalPrivateAttachmentStorage
from services.purge_eligibility import authorize_expired,apply_authorized_tags
from services.continuity_backup import prepare_backup_set,restore_backup_set
from services.continuity_postgres import export_custom,restore_custom

URL=os.environ.get("PHASE29_TEST_DATABASE_URL","").strip()
def _safe_url():
    if not URL:return False
    parsed=urlparse(URL)
    allowed_hosts={"localhost","127.0.0.1","::1"}
    disposable_host=os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST","").strip()
    if disposable_host: allowed_hosts.add(disposable_host)
    if parsed.scheme not in {"postgres","postgresql"} or parsed.hostname not in allowed_hosts or parsed.path!="/frequenia_phase25_test":
        raise RuntimeError("PHASE29_TEST_DATABASE_URL deve usar frequenia_phase25_test local descartável.")
    return True
ENABLED=_safe_url()
if ENABLED: phase25.TEST_DATABASE_URL=URL; phase25.POSTGRES_ENABLED=True

@unittest.skipUnless(ENABLED,"requer PHASE29_TEST_DATABASE_URL explícita")
class Phase29PostgresIntegrationTests(unittest.TestCase):
    for _name in ("COMPANY","UNIT","TEAM","OTHER_TEAM","FOREIGN_COMPANY","FOREIGN_UNIT","FOREIGN_TEAM","EMPLOYEE_USER","EMPLOYEE","OTHER_USER","OTHER_EMPLOYEE","MANAGER_USER","MANAGER","HR_USER","HR","ADMIN_USER","ADMIN","FOREIGN_USER","FOREIGN_EMPLOYEE","FOREIGN_HR_USER","FOREIGN_HR","FOREIGN_ADMIN_USER","FOREIGN_ADMIN","MARKING","EXIT_MARKING","OTHER_MARKING","FOREIGN_MARKING"):
        locals()[_name]=getattr(phase25.Phase25PostgresIntegrationTests,_name)
    del _name
    _seed=phase25.Phase25PostgresIntegrationTests._seed
    _auth=phase25.Phase25PostgresIntegrationTests._auth
    _database_patches=phase25.Phase25PostgresIntegrationTests._database_patches
    _request=phase25.Phase25PostgresIntegrationTests._request
    _create=phase25.Phase25PostgresIntegrationTests._create
    _upload=phase28.Phase28PostgresIntegrationTests._upload
    _rows=phase28.Phase28PostgresIntegrationTests._rows
    @classmethod
    def setUpClass(cls):
        phase25._reset_database(); phase25._apply_migrations(1,24)
        cls.app=Flask("phase29"); cls.app.config.update(TESTING=True,SECRET_KEY="phase29-test"); cls.app.register_blueprint(occurrences_bp)

    def setUp(self):
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:cursor.execute("TRUNCATE empresas,usuarios CASCADE");self._seed(cursor)
            connection.commit()
        finally:connection.close()
        self.temp=tempfile.TemporaryDirectory(prefix="frequenia-phase29-")
        self.env=patch.dict(os.environ,{"APP_ENV":"test","ATTACHMENT_STORAGE_PROVIDER":"local","ATTACHMENT_STORAGE_ROOT":self.temp.name,"ATTACHMENT_SCANNER_PROVIDER":"fake-clean","ATTACHMENT_SCAN_MODE":"async","ATTACHMENT_QUEUE_PROVIDER":"memory"});self.env.start()
        self.storage=LocalPrivateAttachmentStorage(self.temp.name)

    def tearDown(self):self.env.stop();self.temp.cleanup()

    def test_00_migration_024_upgrade_and_clean_install(self):
        phase25._reset_database(); phase25._apply_migrations(1,23)
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:self._seed(cursor)
            connection.commit()
        finally:connection.close()
        correction=self._create(); self._upload(correction); before=self._rows(correction)[0]["id"]
        phase25._apply_migrations(24,24)
        self.assertEqual(self._rows(correction)[0]["id"],before)
        connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.execucoes_continuidade') execution,to_regclass('public.anexo_purge_tag_jobs') tags")
                row=cursor.fetchone(); self.assertIsNotNone(row["execution"]); self.assertIsNotNone(row["tags"])
                cursor.execute("SELECT column_default FROM information_schema.columns WHERE table_name='execucoes_continuidade' AND column_name='created_at'")
                self.assertIn("clock_timestamp",cursor.fetchone()["column_default"])
        finally:connection.close()
        phase25._reset_database(); phase25._apply_migrations(1,24)

    def _make_eligible(self):
        correction=self._create(); self._upload(correction); row=self._rows(correction)[0]
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE anexos_correcao SET estado='substituido',estado_seguranca='limpo',retencao_ate=clock_timestamp()-interval '1 day' WHERE id=%s",(row["id"],))
            connection.commit()
        finally:connection.close()
        return correction,row

    def test_09_operational_history_constraints_and_append_only_evidence(self):
        connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO execucoes_continuidade(tipo,estado,ambiente_logico,integridade_resultado,concluido_at,evidencia_integridade_sha256)
                    VALUES('backup_teste','concluido','test','valido',clock_timestamp(),%s) RETURNING id,created_at""",("a"*64,)); row=cursor.fetchone()
                cursor.execute("INSERT INTO execucoes_continuidade_historico(execucao_id,estado,resultado_codigo) VALUES(%s,'concluido','manifest_valid')",(row["id"],))
            connection.commit(); self.assertIsNotNone(row["created_at"])
            with self.assertRaises(psycopg2.Error):
                with connection.cursor() as cursor: cursor.execute("UPDATE execucoes_continuidade_historico SET resultado_codigo='changed' WHERE execucao_id=%s",(row["id"],))
            connection.rollback()
            with self.assertRaises(psycopg2.Error):
                with connection.cursor() as cursor: cursor.execute("INSERT INTO execucoes_continuidade(tipo,estado,ambiente_logico) VALUES('backup_teste','concluido','test')")
            connection.rollback()
        finally: connection.close()


    def test_10_purge_tagging_dry_run_and_eligibility_guards(self):
        correction,row=self._make_eligible()
        self.assertTrue(authorize_expired(phase25._connect,execute=False)["dry_run"])
        self.assertEqual(apply_authorized_tags(phase25._connect,storage=self.storage,execute=False)["tagged"],0)
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE anexos_correcao SET estado='ativo',estado_seguranca='quarentena' WHERE id=%s",(row["id"],))
            connection.commit()
        finally:connection.close()
        self.assertEqual(authorize_expired(phase25._connect,execute=True)["authorized"],0)
        self.assertFalse(self.storage.is_purge_eligible(row["chave_objeto"]))

    def test_11_eligible_tag_is_post_commit_idempotent_and_auditable(self):
        correction,row=self._make_eligible()
        self.assertEqual(authorize_expired(phase25._connect,execute=True)["authorized"],1)
        connection=phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT purge_autorizado_at FROM anexos_correcao WHERE id=%s",(row["id"],)); self.assertIsNotNone(cursor.fetchone()["purge_autorizado_at"])
        finally:connection.close()
        result=apply_authorized_tags(phase25._connect,storage=self.storage,execute=True)
        self.assertEqual(result["tagged"],1); self.assertTrue(self.storage.is_purge_eligible(row["chave_objeto"]))
        self.assertEqual(apply_authorized_tags(phase25._connect,storage=self.storage,execute=True)["tagged"],0)

    def test_12_tagging_failure_is_retryable_and_concurrency_tags_once(self):
        _,row=self._make_eligible(); authorize_expired(phase25._connect,execute=True)
        class BrokenStorage:
            def read(self,*_):raise AttachmentStorageError("unavailable")
        failed=apply_authorized_tags(phase25._connect,storage=BrokenStorage(),execute=True)
        self.assertEqual(failed["failed"],1); self.assertFalse(self.storage.is_purge_eligible(row["chave_objeto"]))
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:cursor.execute("UPDATE anexo_purge_tag_jobs SET proxima_tentativa_at=clock_timestamp() WHERE anexo_id=%s",(row["id"],))
            connection.commit()
        finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:apply_authorized_tags(phase25._connect,storage=self.storage,execute=True),range(2)))
        self.assertEqual(sum(item["tagged"] for item in results),1)

    def test_13_redrive_plan_validation_terminal_and_success(self):
        correction=self._create(); self._upload(correction); row=self._rows(correction)[0]
        body=build_scan_payload(row["job_id"],row["id"],row["empresa_id"])
        class Source:
            def __init__(self,body):self.messages=[QueueMessage(body,"receipt","message",1)];self.deleted=[]
            def stats(self):return {"dlq":len(self.messages)}
            def receive(self,*_):return list(self.messages)
            def delete(self,receipt):self.deleted.append(receipt);self.messages=[]
        source=Source(body); destination=InMemoryAttachmentQueue()
        self.assertTrue(redrive_messages(phase25._connect,source,destination)["dry_run"]); self.assertEqual(len(source.messages),1)
        with self.assertRaises(RedriveError): redrive_messages(phase25._connect,source,destination,execute=True)
        moved=redrive_messages(phase25._connect,source,destination,True,True,"controlled-test",10)
        self.assertEqual(moved["moved"],1); self.assertEqual(destination.stats()["visible"],1); self.assertEqual(source.deleted,["receipt"])
        terminal=Source(body)
        connection=phase25._connect()
        try:
            with connection.cursor() as cursor:cursor.execute("UPDATE anexo_varredura_jobs SET estado='concluido',concluido_at=clock_timestamp() WHERE id=%s",(row["job_id"],))
            connection.commit()
        finally:connection.close()
        self.assertEqual(redrive_messages(phase25._connect,terminal,destination,True,True,"terminal-test",10)["rejected"],1)
        self.assertEqual(len(terminal.messages),1)

    def test_14_real_pg_dump_manifest_and_isolated_restore(self):
        correction=self._create(); self._upload(correction)
        parsed=urlparse(URL); admin_url=urlunparse(parsed._replace(path="/postgres"))
        restore_name="frequenia_phase29_restore_test"
        restored_url=urlunparse(parsed._replace(path="/"+restore_name))
        source=tempfile.TemporaryDirectory(prefix="frequenia-phase29-export-")
        bundle=tempfile.TemporaryDirectory(prefix="frequenia-phase29-bundle-")
        restored_files=tempfile.TemporaryDirectory(prefix="frequenia-phase29-restored-")
        bundle.cleanup(); restored_files.cleanup()
        admin=psycopg2.connect(admin_url); admin.autocommit=True
        try:
            dump=export_custom(URL,os.path.join(source.name,"database.dump"))
            prepared=prepare_backup_set(bundle.name,[{"source":dump,"component":"postgresql"}],list(range(1,25)),"test",True)
            self.assertTrue(prepared["verified"])
            self.assertTrue(restore_backup_set(bundle.name,restored_files.name,"test",True)["verified"])
            with admin.cursor() as cursor:
                cursor.execute(f'DROP DATABASE IF EXISTS {restore_name}')
                cursor.execute(f'CREATE DATABASE {restore_name}')
            restore_custom(restored_url,os.path.join(restored_files.name,"artifact-0001.bin"))
            restored=psycopg2.connect(restored_url)
            try:
                with restored.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM correcoes WHERE id=%s",(correction,))
                    self.assertEqual(cursor.fetchone()[0],1)
                    cursor.execute("SELECT to_regclass('public.anexo_purge_tag_jobs')")
                    self.assertIsNotNone(cursor.fetchone()[0])
            finally:restored.close()
        finally:
            with admin.cursor() as cursor: cursor.execute(f'DROP DATABASE IF EXISTS {restore_name}')
            admin.close(); source.cleanup()
            if os.path.exists(bundle.name): __import__('shutil').rmtree(bundle.name)
            if os.path.exists(restored_files.name): __import__('shutil').rmtree(restored_files.name)

if __name__=="__main__":unittest.main()
