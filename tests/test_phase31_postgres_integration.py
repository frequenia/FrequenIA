"""Fase 31: integracao opt-in com PostgreSQL/pgvector real e descartavel."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
import unittest
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

import test_phase25_postgres_integration as phase25
from services.biometric_governance import (
    BiometricGovernanceError,
    change_employee_status,
    manage_hold,
    purge_eligible,
    resolve_governance,
    resolve_verification_material,
    transition_biometric,
)


URL = os.environ.get("PHASE31_TEST_DATABASE_URL", "").strip()


def _safe_url():
    if not URL:
        return False
    parsed = urlparse(URL)
    allowed = {"localhost", "127.0.0.1", "::1"}
    explicit = os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST", "").strip()
    if explicit:
        allowed.add(explicit)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in allowed:
        raise RuntimeError("PHASE31_TEST_DATABASE_URL deve apontar para host descartavel local.")
    if parsed.path != "/frequenia_phase25_test":
        raise RuntimeError("PHASE31_TEST_DATABASE_URL deve usar frequenia_phase25_test.")
    return True


ENABLED = _safe_url()
if ENABLED:
    phase25.TEST_DATABASE_URL = URL
    phase25.POSTGRES_ENABLED = True


def connect():
    connection = psycopg2.connect(
        URL, connect_timeout=5, cursor_factory=psycopg2.extras.RealDictCursor,
        options="-c search_path=public,extensions",
    )
    register_vector(connection)
    return connection


@unittest.skipUnless(ENABLED, "requer PHASE31_TEST_DATABASE_URL explicita")
class Phase31PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        phase25._reset_database()
        phase25._apply_migrations(1, 26)

    def setUp(self):
        self.ids = {key: str(uuid4()) for key in (
            "company", "other_company", "unit", "other_unit", "user", "admin",
            "employee", "other_user", "other_employee", "policy", "profile", "biometric",
        )}
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas,usuarios CASCADE")
                self._seed(cursor)
            connection.commit()
        finally:
            connection.close()

    def _seed(self, cursor, *, policy=True, biometric=True):
        i = self.ids
        cursor.execute("INSERT INTO empresas(id,nome) VALUES(%s,'P31'),(%s,'Other')", (i["company"], i["other_company"]))
        cursor.execute("INSERT INTO unidades(id,empresa_id,nome) VALUES(%s,%s,'U'),(%s,%s,'O')", (i["unit"],i["company"],i["other_unit"],i["other_company"]))
        cursor.execute("INSERT INTO usuarios(id,nome,cpf,senha_hash) VALUES(%s,'Synthetic','91000000000','x'),(%s,'Admin','91000000001','x'),(%s,'Other','91000000002','x')", (i["user"],i["admin"],i["other_user"]))
        cursor.execute("""INSERT INTO funcionarios(id,usuario_id,empresa_id,unidade_id,matricula,perfil)
                          VALUES(%s,%s,%s,%s,'P31-1','funcionario'),(%s,%s,%s,%s,'P31-2','funcionario')""",
                       (i["employee"],i["user"],i["company"],i["unit"],i["other_employee"],i["other_user"],i["other_company"],i["other_unit"]))
        if policy:
            cursor.execute("""INSERT INTO politicas_biometricas
                (id,empresa_id,finalidade,versao,referencia_base_legal,versao_aviso,
                 referencia_documental,canal_atendimento,retencao_dias,estado,
                 vigencia_inicio,aprovado_por_usuario_id,aprovado_at)
                VALUES(%s,%s,'registro_ponto_1a1','1','DECISAO-EXTERNA-TESTE','1',
                 'DOC-SINTETICO','/atendimento',30,'aprovada',clock_timestamp()-interval '1 day',%s,clock_timestamp())""",
                (i["policy"],i["company"],i["admin"]))
            cursor.execute("""INSERT INTO perfis_tecnicos_biometricos
                (id,empresa_id,finalidade,versao,modelo,versao_modelo,dimensao,metrica,
                 limiar,versao_liveness,referencia_relatorio,estado,vigencia_inicio,aprovado_por_usuario_id,aprovado_at)
                VALUES(%s,%s,'registro_ponto_1a1','baseline-1','ArcFace','deepface-0.0.99',512,
                 'cosine_distance',0.68,'deepface-0.0.99','CAL-SINTETICA','ativo',clock_timestamp()-interval '1 day',%s,clock_timestamp())""",
                (i["profile"],i["company"],i["admin"]))
        if biometric:
            vector = [1.0] + [0.0] * 511
            cursor.execute("""INSERT INTO biometrias
                (id,empresa_id,funcionario_id,embedding,modelo,versao_modelo,status,
                 politica_biometrica_id,perfil_tecnico_id)
                VALUES(%s,%s,%s,%s,'ArcFace','deepface-0.0.99','ativa',%s,%s)""",
                (i["biometric"],i["company"],i["employee"],vector,
                 i["policy"] if policy else None,i["profile"] if policy else None))

    def test_00_clean_install_and_upgrade_preserve_legacy_biometric(self):
        phase25._reset_database(); phase25._apply_migrations(1, 25)
        marker = str(uuid4())
        connection = psycopg2.connect(URL)
        try:
            with connection.cursor() as c:
                company,unit,user,employee = [str(uuid4()) for _ in range(4)]
                c.execute("INSERT INTO empresas(id,nome) VALUES(%s,'Upgrade')",(company,))
                c.execute("INSERT INTO unidades(id,empresa_id,nome) VALUES(%s,%s,'U')",(unit,company))
                c.execute("INSERT INTO usuarios(id,nome,cpf,senha_hash) VALUES(%s,'Legacy','92000000000','x')",(user,))
                c.execute("INSERT INTO funcionarios(id,usuario_id,empresa_id,unidade_id,matricula) VALUES(%s,%s,%s,%s,'LEG')",(employee,user,company,unit))
                c.execute("INSERT INTO biometrias(id,empresa_id,funcionario_id,embedding,modelo,versao_modelo) VALUES(%s,%s,%s,%s,'ArcFace','legacy')",(marker,company,employee,[1.0]+[0.0]*511))
            connection.commit()
        finally: connection.close()
        phase25._apply_migrations(26,26)
        connection=connect()
        try:
            with connection.cursor() as c:
                c.execute("SELECT status,embedding IS NOT NULL AS material FROM biometrias WHERE id=%s",(marker,))
                self.assertEqual(c.fetchone(), {"status":"ativa","material":True})
        finally: connection.close()

    def test_policy_resolution_and_profile_are_server_authoritative(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                context=resolve_governance(c,self.ids["company"])
                self.assertEqual((context.model,context.dimension,context.threshold),("ArcFace",512,0.68))
        finally: connection.close()

    def test_policy_overlap_and_invalid_threshold_fail_in_database(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                with self.assertRaises(psycopg2.Error):
                    c.execute("""INSERT INTO politicas_biometricas
                    (empresa_id,finalidade,versao,referencia_base_legal,versao_aviso,referencia_documental,
                     canal_atendimento,retencao_dias,estado,vigencia_inicio,aprovado_por_usuario_id,aprovado_at)
                    VALUES(%s,'registro_ponto_1a1','2','X','2','X','X',10,'aprovada',clock_timestamp(),%s,clock_timestamp())""",(self.ids["company"],self.ids["admin"]))
                connection.rollback()
                with self.assertRaises(psycopg2.Error):
                    c.execute("""INSERT INTO perfis_tecnicos_biometricos
                    (empresa_id,finalidade,versao,modelo,versao_modelo,dimensao,metrica,limiar,
                     versao_liveness,referencia_relatorio,estado,vigencia_inicio) VALUES(%s,'x','bad','x','x',512,'cosine_distance','NaN','x','X','rascunho',clock_timestamp())""",(self.ids["company"],))
        finally: connection.close()

    def test_missing_policy_fails_closed_without_default_retention(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                c.execute("DELETE FROM biometrias")
                c.execute("UPDATE politicas_biometricas SET estado='encerrada' WHERE estado='rascunho'")
                c.execute("DELETE FROM perfis_tecnicos_biometricos")
                # A politica aprovada e imutavel; outro tenant sem politica comprova fail-closed.
                with self.assertRaises(BiometricGovernanceError):
                    resolve_governance(c,self.ids["other_company"])
        finally: connection.close()

    def test_verification_requires_active_link_policy_profile_and_exact_versions(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                row,context=resolve_verification_material(c,self.ids["company"],self.ids["employee"])
                self.assertIsNotNone(row["embedding"]); self.assertEqual(context.profile_version,"baseline-1")
                c.execute("UPDATE funcionarios SET status='afastado' WHERE id=%s",(self.ids["employee"],))
                with self.assertRaises(BiometricGovernanceError):
                    resolve_verification_material(c,self.ids["company"],self.ids["employee"])
                connection.rollback()
                c.execute("UPDATE biometrias SET versao_modelo='incompativel' WHERE id=%s",(self.ids["biometric"],))
                with self.assertRaises(BiometricGovernanceError):
                    resolve_verification_material(c,self.ids["company"],self.ids["employee"])
        finally: connection.close()

    def test_block_revoke_pending_are_irreversible_and_idempotent(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                result=transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="bloquear",reason="incidente",idempotency_key="block-key-0001")
                again=transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="bloquear",reason="incidente",idempotency_key="block-key-0001")
                self.assertEqual(result["status"],"bloqueada"); self.assertTrue(again["reutilizada"])
                transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="revogar",reason="solicitacao",idempotency_key="revoke-key-001")
                with self.assertRaises(BiometricGovernanceError):
                    transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="bloquear",reason="incidente",idempotency_key="block-key-0002")
            connection.commit()
        finally: connection.close()

    def test_two_concurrent_enrollments_leave_exactly_one_active_biometric(self):
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM biometrias WHERE empresa_id=%s AND funcionario_id=%s",
                    (self.ids["company"], self.ids["employee"]),
                )
            connection.commit()
        finally:
            connection.close()

        gate = Barrier(2)

        def enroll():
            local = connect()
            try:
                gate.wait(timeout=5)
                with local.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO biometrias
                        (id,empresa_id,funcionario_id,embedding,modelo,versao_modelo,
                         status,politica_biometrica_id,perfil_tecnico_id)
                        VALUES(%s,%s,%s,%s,'ArcFace','deepface-0.0.99','ativa',%s,%s)""",
                        (
                            str(uuid4()), self.ids["company"], self.ids["employee"],
                            [1.0] + [0.0] * 511, self.ids["policy"], self.ids["profile"],
                        ),
                    )
                local.commit()
                return "created"
            except psycopg2.errors.UniqueViolation:
                local.rollback()
                return "conflict"
            finally:
                local.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(lambda _: enroll(), range(2)))
        self.assertEqual(results, ["conflict", "created"])

        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) AS total FROM biometrias
                    WHERE empresa_id=%s AND funcionario_id=%s AND status='ativa'""",
                    (self.ids["company"], self.ids["employee"]),
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
        finally:
            connection.close()

    def test_termination_revokes_biometric_and_all_link_sessions_atomically(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                c.execute("""INSERT INTO auth_sessions(usuario_id,empresa_id,funcionario_id,refresh_token_hash,expires_at)
                             VALUES(%s,%s,%s,%s,clock_timestamp()+interval '1 day'),(%s,%s,%s,%s,clock_timestamp()+interval '1 day')""",
                          (self.ids["user"],self.ids["company"],self.ids["employee"],"a"*64,self.ids["user"],self.ids["company"],self.ids["employee"],"b"*64))
                change_employee_status(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],target_status="desligado",away_policy="bloquear")
                c.execute("SELECT status FROM funcionarios WHERE id=%s",(self.ids["employee"],)); self.assertEqual(c.fetchone()["status"],"desligado")
                c.execute("SELECT status,eliminacao_elegivel_at IS NOT NULL AS scheduled FROM biometrias WHERE id=%s",(self.ids["biometric"],)); self.assertEqual(c.fetchone(),{"status":"revogada","scheduled":True})
                c.execute("SELECT count(*) AS total FROM auth_sessions WHERE funcionario_id=%s AND revoked_at IS NULL",(self.ids["employee"],)); self.assertEqual(c.fetchone()["total"],0)
            connection.rollback()
            with connection.cursor() as c:
                c.execute("SELECT status FROM funcionarios WHERE id=%s",(self.ids["employee"],)); self.assertEqual(c.fetchone()["status"],"ativo")
        finally: connection.close()

    def test_away_policy_is_explicit_and_reactivation_does_not_restore_biometric(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                with self.assertRaises(BiometricGovernanceError):
                    change_employee_status(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],target_status="afastado",away_policy="")
                change_employee_status(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],target_status="afastado",away_policy="bloquear")
                change_employee_status(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],target_status="ativo",away_policy="bloquear")
                c.execute("SELECT status FROM biometrias WHERE id=%s",(self.ids["biometric"],)); self.assertEqual(c.fetchone()["status"],"bloqueada")
        finally: connection.close()

    def test_hold_suspends_elimination_and_release_preserves_history(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="solicitar_exclusao",reason="solicitacao_titular",idempotency_key="delete-key-001")
                c.execute("UPDATE biometrias SET eliminacao_elegivel_at=clock_timestamp()-interval '1 day' WHERE id=%s",(self.ids["biometric"],))
                manage_hold(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="criar_hold",reason="investigacao",reference="CASE-TEST",idempotency_key="hold-key-0001")
            connection.commit()
            self.assertEqual(purge_eligible(connection,company_id=self.ids["company"],execute=True)["eliminadas"],0)
            with connection.cursor() as c:
                manage_hold(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="cancelar_hold",reason="encerrada",reference="CASE-TEST",idempotency_key="hold-key-0002")
            connection.commit()
            self.assertEqual(purge_eligible(connection,company_id=self.ids["company"],execute=True)["eliminadas"],1)
            with connection.cursor() as c:
                c.execute("SELECT status,embedding,referencia_arquivo_privado FROM biometrias WHERE id=%s",(self.ids["biometric"],)); row=c.fetchone()
                self.assertEqual(row["status"],"eliminada"); self.assertIsNone(row["embedding"]); self.assertIsNone(row["referencia_arquivo_privado"])
                c.execute("SELECT count(*) AS total FROM holds_biometricos WHERE biometria_id=%s",(self.ids["biometric"],)); self.assertEqual(c.fetchone()["total"],1)
        finally: connection.close()

    def test_dry_run_and_concurrent_purge_process_once(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                transition_biometric(c,company_id=self.ids["company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="solicitar_exclusao",reason="solicitacao_titular",idempotency_key="delete-key-002")
                c.execute("UPDATE biometrias SET eliminacao_elegivel_at=clock_timestamp()-interval '1 day' WHERE id=%s",(self.ids["biometric"],))
            connection.commit()
            self.assertEqual(purge_eligible(connection,company_id=self.ids["company"]),{"dry_run":True,"elegiveis":1,"eliminadas":0})
        finally: connection.close()
        def run():
            local=connect()
            try: return purge_eligible(local,company_id=self.ids["company"],execute=True)["eliminadas"]
            finally: local.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: run(),range(2))),1)

    def test_nested_sensitive_audit_metadata_is_rejected(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                with self.assertRaises(psycopg2.Error):
                    c.execute("INSERT INTO auditoria(empresa_id,acao,entidade_tipo,metadados) VALUES(%s,'x','x',%s::jsonb)",(self.ids["company"],'{"nested":{"embedding":"forbidden"}}'))
        finally: connection.close()

    def test_cross_tenant_is_non_enumerable_at_service_boundary(self):
        connection=connect()
        try:
            with connection.cursor() as c:
                with self.assertRaises(BiometricGovernanceError) as error:
                    transition_biometric(c,company_id=self.ids["other_company"],employee_id=self.ids["employee"],actor_id=self.ids["admin"],operation="bloquear",reason="incidente",idempotency_key="foreign-key-01")
                self.assertEqual(error.exception.status,404)
        finally: connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
