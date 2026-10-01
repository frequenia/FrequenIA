import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "facial-failure-workflow-test-key")

from routes.occurrences import occurrences_bp
from services.facial_failure_workflow import (
    FacialFailureWorkflowError,
    transition_facial_failure_occurrence,
)


COMPANY = "00000000-0000-0000-0000-000000000301"
MANAGER = "00000000-0000-0000-0000-000000000302"
USER = "00000000-0000-0000-0000-000000000303"
OCCURRENCE = "00000000-0000-0000-0000-000000000304"
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


def auth(role="gestor"):
    return {
        "user_id": USER,
        "funcionario_id": MANAGER,
        "empresa_id": COMPANY,
        "session_id": "00000000-0000-0000-0000-000000000305",
        "familia_id": "00000000-0000-0000-0000-000000000306",
        "perfil": role,
    }


def updated(state, decision=None):
    return {
        "id": OCCURRENCE,
        "estado": state,
        "responsavel_usuario_id": USER,
        "decisao": decision,
        "resolved_at": NOW if state in ("resolvida", "descartada") else None,
        "updated_at": NOW,
    }


class Cursor:
    def __init__(self, rows=None, fail_on=None):
        self.rows = list(rows or [])
        self.calls = []
        self.fail_on = fail_on

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if self.fail_on and self.fail_on in normalized:
            raise RuntimeError("database failure")

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

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


class FacialFailureWorkflowDomainTests(unittest.TestCase):
    def transition(self, current, target, justification=None, role="gestor", fail_on=None):
        cursor = Cursor(
            rows=[{"id": OCCURRENCE, "estado": current}, updated(target, justification)],
            fail_on=fail_on,
        )
        connection = Connection(cursor)
        with patch(
            "services.facial_failure_workflow.conectar_bd", return_value=connection
        ):
            result = transition_facial_failure_occurrence(
                auth(role), OCCURRENCE, target, justification
            )
        return result, connection

    def test_every_allowed_transition_commits_and_audits(self):
        cases = (
            ("aberta", "em_analise", None),
            ("aberta", "resolvida", "Validada com a liderança."),
            ("aberta", "descartada", "Evento sem ação necessária."),
            ("em_analise", "resolvida", "Análise concluída."),
            ("em_analise", "descartada", "Descartada após análise."),
        )
        for current, target, reason in cases:
            with self.subTest(current=current, target=target):
                result, connection = self.transition(current, target, reason)
                self.assertEqual(result["estado"], target)
                self.assertEqual(connection.commits, 1)
                self.assertEqual(connection.rollbacks, 0)
                sql = " ".join(call[0] for call in connection.test_cursor.calls)
                self.assertIn("FOR UPDATE OF o", sql)
                self.assertIn("INSERT INTO auditoria", sql)
                self.assertIn("clock_timestamp()", sql)
                audit = connection.test_cursor.calls[-1][1]
                self.assertEqual(audit[:4], (
                    COMPANY,
                    USER,
                    f"ocorrencia.falha_facial.{target}",
                    OCCURRENCE,
                ))
                self.assertEqual(audit[4].adapted["estado_anterior"], current)
                self.assertEqual(audit[4].adapted["estado_novo"], target)

    def test_final_states_and_repeated_transition_return_conflict(self):
        for current, target in (
            ("resolvida", "descartada"),
            ("descartada", "resolvida"),
            ("em_analise", "em_analise"),
        ):
            cursor = Cursor(rows=[{"id": OCCURRENCE, "estado": current}])
            connection = Connection(cursor)
            with patch(
                "services.facial_failure_workflow.conectar_bd",
                return_value=connection,
            ), self.assertRaises(FacialFailureWorkflowError) as raised:
                transition_facial_failure_occurrence(
                    auth(), OCCURRENCE, target, "Justificativa"
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(connection.commits, 0)
            self.assertEqual(connection.rollbacks, 1)
            self.assertEqual(len(cursor.calls), 1)

    def test_final_transition_requires_trimmed_justification_before_database(self):
        for target in ("resolvida", "descartada"):
            with patch("services.facial_failure_workflow.conectar_bd") as connect:
                with self.assertRaises(FacialFailureWorkflowError) as raised:
                    transition_facial_failure_occurrence(auth(), OCCURRENCE, target, "  ")
            self.assertEqual(raised.exception.status_code, 400)
            connect.assert_not_called()

    def test_manager_lock_combines_company_and_scope(self):
        _, connection = self.transition("aberta", "em_analise")
        sql, params = connection.test_cursor.calls[0]
        self.assertIn("gestores_escopos", sql)
        self.assertIn("FOR UPDATE OF o", sql)
        self.assertEqual(params[0:2], (OCCURRENCE, COMPANY))
        self.assertIn(MANAGER, params)

    def test_hr_and_admin_are_still_limited_to_session_company(self):
        for role in ("rh", "administrador"):
            _, connection = self.transition("aberta", "em_analise", role=role)
            sql, params = connection.test_cursor.calls[0]
            self.assertNotIn("gestores_escopos", sql)
            self.assertEqual(params, (OCCURRENCE, COMPANY))

    def test_out_of_scope_is_non_disclosing_404(self):
        cursor = Cursor(rows=[])
        connection = Connection(cursor)
        with patch(
            "services.facial_failure_workflow.conectar_bd", return_value=connection
        ), self.assertRaises(FacialFailureWorkflowError) as raised:
            transition_facial_failure_occurrence(auth(), OCCURRENCE, "em_analise")
        self.assertEqual(raised.exception.status_code, 404)
        self.assertNotIn("empresa", raised.exception.message.lower())
        self.assertEqual(connection.rollbacks, 1)

    def test_audit_failure_rolls_back_state_update_atomically(self):
        cursor = Cursor(
            rows=[{"id": OCCURRENCE, "estado": "aberta"}, updated("resolvida", "Motivo")],
            fail_on="INSERT INTO auditoria",
        )
        connection = Connection(cursor)
        with patch(
            "services.facial_failure_workflow.conectar_bd", return_value=connection
        ), self.assertRaises(RuntimeError):
            transition_facial_failure_occurrence(
                auth(), OCCURRENCE, "resolvida", "Motivo"
            )
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)


class FacialFailureWorkflowRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(occurrences_bp)
        self.client = self.app.test_client()

    def request_as(self, action, role="gestor", body=None):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth(role), None),
        ):
            return self.client.post(
                f"/api/gestao/ocorrencias/falhas-faciais/{OCCURRENCE}/{action}",
                headers={"Authorization": "Bearer test"},
                json=body,
            )

    def test_explicit_endpoints_map_to_domain_targets(self):
        cases = (
            ("iniciar-analise", "em_analise", None),
            ("resolver", "resolvida", "Resolvida após análise."),
            ("descartar", "descartada", "Descartada após validação."),
        )
        for action, target, reason in cases:
            with self.subTest(action=action), patch(
                "routes.occurrences.transition_facial_failure_occurrence",
                return_value=updated(target, reason),
            ) as transition:
                body = {"justificativa": reason} if reason else {}
                response = self.request_as(action, body=body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["estado"], target)
            self.assertEqual(transition.call_args.args, (auth(), OCCURRENCE, target, reason))

    def test_resolve_and_discard_require_justification(self):
        for action in ("resolver", "descartar"):
            with patch(
                "routes.occurrences.transition_facial_failure_occurrence"
            ) as transition:
                response = self.request_as(action, body={})
            self.assertEqual(response.status_code, 400)
            transition.assert_not_called()

    def test_common_employee_cannot_act(self):
        with patch("routes.occurrences.transition_facial_failure_occurrence") as transition:
            response = self.request_as("iniciar-analise", role="funcionario", body={})
        self.assertEqual(response.status_code, 403)
        transition.assert_not_called()

    def test_domain_conflict_is_preserved_as_409(self):
        with patch(
            "routes.occurrences.transition_facial_failure_occurrence",
            side_effect=FacialFailureWorkflowError(
                "A ocorrência foi alterada ou não permite esta transição.", 409
            ),
        ):
            response = self.request_as(
                "resolver", body={"justificativa": "Decisão concorrente."}
            )
        self.assertEqual(response.status_code, 409)

    def test_migration_preserves_general_archive_and_restricts_facial_states(self):
        migration = (
            Path(__file__).parents[1]
            / "supabase"
            / "migrations"
            / "017_facial_failure_workflow.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("'arquivada', 'descartada'", migration)
        self.assertIn("ocorrencias_falha_facial_estado_check", migration)
        self.assertIn("ocorrencias_descartada_tipo_check", migration)
        self.assertIn("responsavel_usuario_id is not null", migration)
        self.assertIn("resolved_at is not null", migration)


if __name__ == "__main__":
    unittest.main()
