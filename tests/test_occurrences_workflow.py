import os
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask, g

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "occurrence-test-jwt-key")

from routes.occurrences import (
    _transition,
    _validate_request,
    occurrences_bp,
)
from routes.timekeeping import _serialize_daily_records
from services.effective_timekeeping import fetch_effective_events

COMPANY = "00000000-0000-0000-0000-000000000001"
EMPLOYEE = "00000000-0000-0000-0000-000000000002"
USER = "00000000-0000-0000-0000-000000000003"
CORRECTION = "00000000-0000-0000-0000-000000000004"
MARKING = "00000000-0000-0000-0000-000000000005"


def context(role="funcionario"):
    return {
        "user_id": USER,
        "funcionario_id": EMPLOYEE,
        "empresa_id": COMPANY,
        "session_id": "00000000-0000-0000-0000-000000000006",
        "familia_id": "00000000-0000-0000-0000-000000000007",
        "perfil": role,
    }


def correction_row(state="solicitada", operation="alteracao_instante"):
    return {
        "id": CORRECTION,
        "empresa_id": COMPANY,
        "funcionario_id": EMPLOYEE,
        "solicitante_usuario_id": USER,
        "ocorrencia_id": "00000000-0000-0000-0000-000000000008",
        "marcacao_original_id": MARKING if operation != "inclusao" else None,
        "tipo": operation,
        "categoria": "horario_incorreto",
        "motivo": "Falha no aplicativo",
        "estado": state,
        "instante_proposto": datetime(2026, 9, 12, 11, 2, tzinfo=timezone.utc),
        "tipo_marcacao_proposto": None,
        "created_at": datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
        "decided_at": None,
        "decisao": None,
    }


class Cursor:
    def __init__(self, one=None, all_rows=None):
        self.one = list(one or [])
        self.all_rows = all_rows or []
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.one.pop(0) if self.one else None

    def fetchall(self):
        return self.all_rows

    def close(self):
        pass


class Connection:
    def __init__(self, cursor):
        self.test_cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_kwargs):
        return self.test_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class ValidationTests(unittest.TestCase):
    def test_categories_map_to_operations_and_require_specific_fields(self):
        result = _validate_request({
            "tipo": "esquecimento_marcacao", "motivo": "Esqueci",
            "instante_solicitado": "2026-09-12T08:00:00-03:00",
            "tipo_marcacao_solicitado": "entrada",
        })
        self.assertEqual(result[1], "inclusao")
        self.assertIsNone(result[2])
        self.assertEqual(result[4].tzinfo, timezone.utc)
        self.assertEqual(
            _validate_request({"tipo": "justificativa", "motivo": "Trânsito"})[1],
            "justificativa",
        )
        with self.assertRaisesRegex(ValueError, "timezone"):
            _validate_request({"tipo": "esquecimento_marcacao", "motivo": "x", "instante_solicitado": "2026-09-12T08:00:00", "tipo_marcacao_solicitado": "entrada"})
        with self.assertRaises(ValueError):
            _validate_request({"tipo": "tipo_invalido", "motivo": "x"})

    def test_each_change_category_requires_original_marking(self):
        with self.assertRaises(ValueError):
            _validate_request({"tipo": "horario_incorreto", "motivo": "x", "instante_solicitado": "2026-09-12T08:00:00Z"})
        with self.assertRaises(ValueError):
            _validate_request({"tipo": "tipo_incorreto", "motivo": "x", "tipo_marcacao_solicitado": "saida"})

    def test_change_categories_reject_fields_that_would_not_be_applied(self):
        valid_time = {
            "tipo": "horario_incorreto", "motivo": "Ajuste", "marcacao_id": MARKING,
            "instante_solicitado": "2026-09-12T08:00:00-03:00",
        }
        valid_type = {
            "tipo": "tipo_incorreto", "motivo": "Ajuste", "marcacao_id": MARKING,
            "tipo_marcacao_solicitado": "entrada",
        }
        self.assertEqual(_validate_request(valid_time)[1], "alteracao_instante")
        self.assertEqual(_validate_request(valid_type)[1], "alteracao_tipo")
        with self.assertRaisesRegex(ValueError, "não aceita tipo"):
            _validate_request({**valid_time, "tipo_marcacao_solicitado": "entrada"})
        with self.assertRaisesRegex(ValueError, "não aceita instante"):
            _validate_request({**valid_type, "instante_solicitado": "2026-09-12T08:00:00-03:00"})


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path(__file__).parents[1] / "templates"))
        self.app.register_blueprint(occurrences_bp)
        self.client = self.app.test_client()

    def auth(self, role="funcionario"):
        return patch("utils.auth_decorator._load_persistent_authentication", return_value=(context(role), None))

    def test_personal_creation_uses_session_identity_and_audits(self):
        row = correction_row(operation="inclusao")
        row["categoria"] = "esquecimento_marcacao"
        row["tipo_marcacao_proposto"] = "entrada"
        connection = Connection(Cursor(one=[{"id": "00000000-0000-0000-0000-000000000008"}, row]))
        with self.auth(), patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.client.post("/api/ocorrencias", headers={"Authorization": "Bearer x"}, json={"tipo":"esquecimento_marcacao","motivo":"Esqueci","instante_solicitado":"2026-09-12T08:00:00-03:00","tipo_marcacao_solicitado":"entrada"})
        self.assertEqual(response.status_code, 201)
        insert = connection.test_cursor.calls[1]
        self.assertIn("INSERT INTO correcoes", insert[0])
        self.assertEqual(insert[1][0:2], (COMPANY, EMPLOYEE))
        self.assertEqual(insert[1][4], USER)
        self.assertTrue(any("INSERT INTO auditoria" in sql for sql, _ in connection.test_cursor.calls))
        self.assertEqual(connection.commits, 1)

    def test_server_identity_fields_are_rejected_before_database(self):
        with self.auth(), patch("routes.occurrences.conectar_bd") as connect:
            response = self.client.post("/api/ocorrencias", headers={"Authorization":"Bearer x"}, json={"tipo":"justificativa","motivo":"x","empresa_id":COMPANY})
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    def test_inapplicable_change_fields_return_400_before_any_persistence(self):
        payloads = (
            {"tipo": "horario_incorreto", "motivo": "Ajuste", "marcacao_id": MARKING,
             "instante_solicitado": "2026-09-12T08:00:00-03:00",
             "tipo_marcacao_solicitado": "entrada"},
            {"tipo": "tipo_incorreto", "motivo": "Ajuste", "marcacao_id": MARKING,
             "tipo_marcacao_solicitado": "entrada",
             "instante_solicitado": "2026-09-12T08:00:00-03:00"},
        )
        for payload in payloads:
            with self.subTest(category=payload["tipo"]), self.auth(), \
                    patch("routes.occurrences.conectar_bd") as connect:
                response = self.client.post(
                    "/api/ocorrencias", headers={"Authorization": "Bearer x"}, json=payload,
                )
                self.assertEqual(response.status_code, 400)
                connect.assert_not_called()

    def test_foreign_or_missing_marking_is_indistinguishable(self):
        connection = Connection(Cursor(one=[None]))
        with self.auth(), patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.client.post("/api/ocorrencias", headers={"Authorization":"Bearer x"}, json={"tipo":"horario_incorreto","motivo":"x","marcacao_id":MARKING,"instante_solicitado":"2026-09-12T08:00:00Z"})
        self.assertEqual(response.status_code, 404)
        query, params = connection.test_cursor.calls[0]
        self.assertIn("empresa_id = %s", query)
        self.assertIn("funcionario_id = %s", query)
        self.assertEqual(params, (MARKING, COMPANY, EMPLOYEE))

    def test_management_rbac_and_page(self):
        with self.auth("funcionario"):
            self.assertEqual(self.client.get("/api/gestao/ocorrencias", headers={"Authorization":"Bearer x"}).status_code, 403)
        for role in ("administrador", "gestor", "rh"):
            connection = Connection(Cursor(all_rows=[]))
            with self.auth(role), patch("routes.occurrences.conectar_bd", return_value=connection):
                self.assertEqual(self.client.get("/api/gestao/ocorrencias", headers={"Authorization":"Bearer x"}).status_code, 200)
                self.assertEqual(connection.test_cursor.calls[0][1][0], COMPANY)

    def test_invalid_uuid_is_controlled(self):
        with self.auth("gestor"), patch("routes.occurrences.conectar_bd") as connect:
            response = self.client.get("/api/gestao/ocorrencias/not-a-uuid", headers={"Authorization":"Bearer x"})
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()

    def test_rejection_requires_observation(self):
        with self.auth("rh"), patch("routes.occurrences.conectar_bd") as connect:
            response = self.client.post(f"/api/gestao/ocorrencias/{CORRECTION}/rejeitar", headers={"Authorization":"Bearer x"}, json={})
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()


class TransitionAndEffectiveViewTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_approval_locks_updates_audits_notifies_and_never_updates_marking(self):
        original = correction_row()
        updated = dict(original, estado="aprovada", decisao="Aprovado", decided_at=datetime.now(timezone.utc))
        cursor = Cursor(one=[original, {"id": MARKING}, updated])
        connection = Connection(cursor)
        with self.app.test_request_context(), patch("routes.occurrences.conectar_bd", return_value=connection):
            g.auth_context = context("gestor")
            body, status = _transition(CORRECTION, "aprovada", "Aprovado")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "aprovada")
        sql = " ".join(call[0] for call in cursor.calls)
        self.assertIn("SELECT * FROM correcoes", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("clock_timestamp()", sql)
        self.assertIn("INSERT INTO auditoria", sql)
        self.assertIn("INSERT INTO notificacoes", sql)
        self.assertNotIn("UPDATE marcacoes", sql)
        self.assertEqual(connection.commits, 1)

    def test_only_pending_request_can_be_decided(self):
        connection = Connection(Cursor(one=[correction_row("aprovada")]))
        with self.app.test_request_context(), patch("routes.occurrences.conectar_bd", return_value=connection):
            g.auth_context = context("administrador")
            _, status = _transition(CORRECTION, "rejeitada", "Não aprovada")
        self.assertEqual(status, 409)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    def test_effective_query_is_tenant_scoped_deterministic_and_approved_only(self):
        cursor = Cursor(all_rows=[])
        fetch_effective_events(cursor, COMPANY, EMPLOYEE)
        sql, params = cursor.calls[0]
        self.assertIn("FROM marcacoes", sql)
        self.assertIn("FROM correcoes", sql)
        self.assertIn("estado = 'aprovada'", sql)
        self.assertIn("ajuste_administrativo", sql)
        self.assertIn("ORDER BY instante ASC, id ASC", sql)
        self.assertEqual(params[0:4], (COMPANY, EMPLOYEE, COMPANY, EMPLOYEE))

    def test_adjusted_event_preserves_timezone_and_marks_daily_view(self):
        records = _serialize_daily_records([{"id":"ajuste:1","tipo":"entrada","instante":datetime(2026,9,13,1,30,tzinfo=timezone.utc),"ajustada":True}])
        self.assertEqual(records[0]["data"], "2026-09-12")
        self.assertEqual(records[0]["entrada"], "22:30")
        self.assertTrue(records[0]["ajustada"])
        self.assertEqual(records[0]["ajustes"], ["entrada"])

    def test_migration_is_incremental_and_protects_approved_conflicts(self):
        migration = (Path(__file__).parents[1] / "supabase/migrations/012_occurrence_correction_workflow.sql").read_text(encoding="utf-8")
        self.assertIn("add column categoria", migration.lower())
        self.assertIn("create unique index", migration.lower())
        self.assertNotIn("update public.marcacoes", migration.lower())
        self.assertNotIn("delete from public.marcacoes", migration.lower())


if __name__ == "__main__":
    unittest.main()
