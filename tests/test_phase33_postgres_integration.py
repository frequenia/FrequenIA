"""Fase 33: reconciliacao biometrica opt-in em PostgreSQL descartavel."""

import unittest
from uuid import uuid4

import test_phase31_postgres_integration as phase31
from services.biometric_governance import (
    BiometricGovernanceError,
    purge_eligible,
    reconcile_restored_biometrics,
    transition_biometric,
)


@unittest.skipUnless(
    phase31.ENABLED, "requer PHASE31_TEST_DATABASE_URL explicita"
)
class Phase33PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        phase31.phase25._reset_database()
        phase31.phase25._apply_migrations(1, 26)

    def setUp(self):
        self.ids = {key: str(uuid4()) for key in (
            "company", "other_company", "unit", "other_unit", "user", "admin",
            "employee", "other_user", "other_employee", "policy", "profile",
            "biometric",
        )}
        helper = phase31.Phase31PostgresIntegrationTests()
        helper.ids = self.ids
        connection = phase31.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas,usuarios CASCADE")
                helper._seed(cursor)
            connection.commit()
        finally:
            connection.close()

    def test_eliminated_history_removes_material_resurrected_by_partial_restore(self):
        connection = phase31.connect()
        try:
            with connection.cursor() as cursor:
                transition_biometric(
                    cursor,
                    company_id=self.ids["company"],
                    employee_id=self.ids["employee"],
                    actor_id=self.ids["admin"],
                    operation="solicitar_exclusao",
                    reason="solicitacao_titular",
                    idempotency_key="phase33-delete-001",
                )
                cursor.execute(
                    """UPDATE biometrias
                       SET eliminacao_elegivel_at=clock_timestamp()-interval '1 day'
                       WHERE id=%s""",
                    (self.ids["biometric"],),
                )
            connection.commit()

            purged = purge_eligible(
                connection, company_id=self.ids["company"], execute=True
            )
            self.assertEqual(purged["eliminadas"], 1)

            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE biometrias
                       SET status='ativa',embedding=%s,eliminada_at=NULL,
                           motivo_codigo='restore_parcial',updated_at=clock_timestamp()
                       WHERE empresa_id=%s AND id=%s""",
                    (
                        [1.0] + [0.0] * 511,
                        self.ids["company"],
                        self.ids["biometric"],
                    ),
                )
            connection.commit()

            dry_run = reconcile_restored_biometrics(
                connection, company_id=self.ids["company"]
            )
            self.assertEqual(dry_run["eliminacoes_autoritativas"], 1)
            self.assertEqual(dry_run["reparadas"], 0)

            repaired = reconcile_restored_biometrics(
                connection, company_id=self.ids["company"], execute=True
            )
            self.assertEqual(repaired["reparadas"], 1)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status,embedding,referencia_arquivo_privado
                       FROM biometrias WHERE empresa_id=%s AND id=%s""",
                    (self.ids["company"], self.ids["biometric"]),
                )
                self.assertEqual(cursor.fetchone(), {
                    "status": "eliminada",
                    "embedding": None,
                    "referencia_arquivo_privado": None,
                })

            repeated = reconcile_restored_biometrics(
                connection, company_id=self.ids["company"], execute=True
            )
            self.assertEqual(repeated["reparadas"], 0)
            self.assertEqual(repeated["divergencias"], 0)
        finally:
            connection.close()

    def test_idempotency_key_cannot_cross_employee_within_tenant(self):
        connection = phase31.connect()
        try:
            second_user = str(uuid4())
            second_employee = str(uuid4())
            second_biometric = str(uuid4())
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO usuarios(id,nome,cpf,senha_hash) VALUES(%s,'Synthetic 2','91000000009','x')",
                    (second_user,),
                )
                cursor.execute(
                    """INSERT INTO funcionarios
                       (id,usuario_id,empresa_id,unidade_id,matricula,perfil)
                       VALUES(%s,%s,%s,%s,'P33-2','funcionario')""",
                    (
                        second_employee,
                        second_user,
                        self.ids["company"],
                        self.ids["unit"],
                    ),
                )
                cursor.execute(
                    """INSERT INTO biometrias
                       (id,empresa_id,funcionario_id,embedding,modelo,versao_modelo,
                        status,politica_biometrica_id,perfil_tecnico_id)
                       VALUES(%s,%s,%s,%s,'ArcFace','deepface-0.0.99','ativa',%s,%s)""",
                    (
                        second_biometric,
                        self.ids["company"],
                        second_employee,
                        [0.0, 1.0] + [0.0] * 510,
                        self.ids["policy"],
                        self.ids["profile"],
                    ),
                )
                transition_biometric(
                    cursor,
                    company_id=self.ids["company"],
                    employee_id=self.ids["employee"],
                    actor_id=self.ids["admin"],
                    operation="bloquear",
                    reason="incidente",
                    idempotency_key="phase33-shared-key",
                )
                with self.assertRaises(BiometricGovernanceError) as error:
                    transition_biometric(
                        cursor,
                        company_id=self.ids["company"],
                        employee_id=second_employee,
                        actor_id=self.ids["admin"],
                        operation="bloquear",
                        reason="incidente",
                        idempotency_key="phase33-shared-key",
                    )
                self.assertEqual(error.exception.code, "idempotencia_conflitante")
            connection.rollback()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
