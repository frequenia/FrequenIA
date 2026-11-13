"""Regressoes locais da Fase 33 sem imagens ou dados biometricos reais."""

import inspect
import unittest

from services.biometric_governance import reconcile_restored_biometrics
from services import biometric_governance


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        self.rowcount = 1 if normalized.startswith("UPDATE biometrias") else 0

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.cursor_value = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_kwargs):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Phase33BiometricReliabilityTests(unittest.TestCase):
    def test_idempotency_reuse_is_bound_to_employee(self):
        source = inspect.getsource(biometric_governance.transition_biometric)
        hold_source = inspect.getsource(biometric_governance.manage_hold)
        for implementation in (source, hold_source):
            self.assertIn('prior["funcionario_id"]', implementation)
            self.assertIn("idempotencia_conflitante", implementation)

    def test_reconciliation_is_tenant_scoped_locked_and_dry_run_by_default(self):
        signature = inspect.signature(reconcile_restored_biometrics)
        self.assertFalse(signature.parameters["execute"].default)
        source = inspect.getsource(reconcile_restored_biometrics)
        self.assertIn("h.empresa_id=%s", source)
        self.assertIn("b.empresa_id=%s", source)
        self.assertIn("SKIP LOCKED", source)

        connection = FakeConnection([
            {
                "id": "bio-a",
                "status": "ativa",
                "estado_novo": "eliminada",
                "ocorrido_at": None,
                "material_presente": True,
            }
        ])
        result = reconcile_restored_biometrics(connection, company_id="tenant-a")

        self.assertEqual(result["eliminacoes_autoritativas"], 1)
        self.assertEqual(result["reparadas"], 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertEqual(connection.commits, 0)
        self.assertFalse(any(sql.startswith("UPDATE") for sql, _ in connection.cursor_value.calls))

    def test_reconciliation_repairs_only_authoritative_deletion_and_returns_aggregates(self):
        connection = FakeConnection([
            {
                "id": "bio-a",
                "status": "ativa",
                "estado_novo": "eliminada",
                "ocorrido_at": None,
                "material_presente": True,
            },
            {
                "id": "bio-b",
                "status": "ativa",
                "estado_novo": "revogada",
                "ocorrido_at": None,
                "material_presente": True,
            },
        ])

        result = reconcile_restored_biometrics(
            connection, company_id="tenant-a", execute=True
        )

        updates = [sql for sql, _ in connection.cursor_value.calls if sql.startswith("UPDATE")]
        self.assertEqual(len(updates), 1)
        self.assertEqual(result, {
            "dry_run": False,
            "divergencias": 2,
            "eliminacoes_autoritativas": 1,
            "pendentes_manuais": 1,
            "reparadas": 1,
        })
        self.assertEqual(connection.commits, 1)
        self.assertNotIn("id", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
