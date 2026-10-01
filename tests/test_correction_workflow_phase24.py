"""Contrato unitario do workflow definitivo de correcoes da Fase 24."""

from datetime import datetime, timezone
from pathlib import Path
import unittest

from services.correction_workflow import (
    CorrectionWorkflowError,
    allowed_actions,
    normalize_justification,
    transition_correction,
)


COMPANY = "00000000-0000-0000-0000-000000000001"
EMPLOYEE = "00000000-0000-0000-0000-000000000002"
USER = "00000000-0000-0000-0000-000000000003"
CORRECTION = "00000000-0000-0000-0000-000000000004"
MARKING = "00000000-0000-0000-0000-000000000005"


def auth(role):
    return {
        "empresa_id": COMPANY,
        "funcionario_id": EMPLOYEE,
        "user_id": USER,
        "perfil": role,
    }


def row(state="pendente_gestor"):
    return {
        "id": CORRECTION,
        "empresa_id": COMPANY,
        "funcionario_id": EMPLOYEE,
        "solicitante_usuario_id": USER,
        "ocorrencia_id": "00000000-0000-0000-0000-000000000006",
        "marcacao_original_id": MARKING,
        "tipo": "alteracao_instante",
        "categoria": "horario_incorreto",
        "motivo": "Ajuste",
        "estado": state,
        "instante_proposto": datetime(2026, 9, 12, 11, tzinfo=timezone.utc),
        "tipo_marcacao_proposto": None,
        "created_at": datetime(2026, 9, 12, 12, tzinfo=timezone.utc),
        "decided_at": None,
        "decisao": None,
    }


class Cursor:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.results.pop(0) if self.results else None

    def close(self):
        pass


class Connection:
    def __init__(self, results):
        self.cursor_value = Cursor(results)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_kwargs):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def run_transition(role, state, target, observation=None, own=False):
    original = row(state)
    updated = dict(original, estado=target, decisao=observation)
    results = [original]
    if target == "aprovada":
        results.append({"id": MARKING})
    results.append(updated)
    connection = Connection(results)
    result = transition_correction(
        lambda: connection, auth(role), CORRECTION, target, observation, own
    )
    return result, connection


class WorkflowPolicyTests(unittest.TestCase):
    def test_allowed_transitions_are_role_and_state_specific(self):
        self.assertEqual(
            allowed_actions("gestor", "pendente_gestor"),
            ["aprovar", "rejeitar", "encaminhar-rh"],
        )
        self.assertEqual(allowed_actions("rh", "pendente_gestor"), [])
        self.assertEqual(
            allowed_actions("rh", "encaminhada_rh"), ["aprovar", "rejeitar"]
        )
        self.assertEqual(
            allowed_actions("administrador", "encaminhada_rh"),
            ["aprovar", "rejeitar"],
        )
        self.assertEqual(allowed_actions("gestor", "encaminhada_rh"), [])
        self.assertEqual(allowed_actions("funcionario", "pendente_gestor", own=True), ["cancelar"])
        for final in ("aprovada", "rejeitada", "cancelada"):
            self.assertEqual(allowed_actions("gestor", final), [])

    def test_manager_forwards_and_audit_is_complete_and_database_timestamped(self):
        result, connection = run_transition(
            "gestor", "pendente_gestor", "encaminhada_rh", "  Revisar   documento  "
        )
        self.assertEqual(result["estado"], "encaminhada_rh")
        self.assertEqual(connection.commits, 1)
        sql = " ".join(call[0] for call in connection.cursor_value.calls)
        self.assertIn("FOR UPDATE OF c", sql)
        self.assertIn("clock_timestamp()", sql)
        audit_call = next(call for call in connection.cursor_value.calls if "INSERT INTO auditoria" in call[0])
        self.assertNotIn("ocorrido_at", audit_call[0])
        metadata = audit_call[1][-1].adapted
        self.assertEqual(metadata["estado_anterior"], "pendente_gestor")
        self.assertEqual(metadata["estado_novo"], "encaminhada_rh")
        self.assertEqual(metadata["papel"], "gestor")
        self.assertEqual(metadata["justificativa"], "Revisar documento")
        self.assertEqual(metadata["empresa_id"], COMPANY)
        self.assertEqual(metadata["funcionario_id"], EMPLOYEE)

    def test_hr_and_admin_only_decide_forwarded_requests(self):
        for role in ("rh", "administrador"):
            with self.subTest(role=role):
                result, connection = run_transition(
                    role, "encaminhada_rh", "aprovada", "Conferido"
                )
                self.assertEqual(result["estado"], "aprovada")
                sql = " ".join(call[0] for call in connection.cursor_value.calls)
                self.assertNotIn("UPDATE marcacoes", sql)

        for role in ("rh", "administrador"):
            connection = Connection([row("pendente_gestor")])
            with self.subTest(role=role), self.assertRaises(CorrectionWorkflowError):
                transition_correction(
                    lambda: connection,
                    auth(role),
                    CORRECTION,
                    "aprovada",
                    "Tentativa direta",
                )
            self.assertEqual(connection.commits, 0)
            self.assertEqual(connection.rollbacks, 1)

    def test_rejection_and_forward_require_normalized_bounded_observation(self):
        self.assertEqual(normalize_justification("  texto\n  valido ", True), "texto valido")
        for target in ("rejeitada", "encaminhada_rh"):
            connection = Connection([])
            with self.subTest(target=target), self.assertRaises(CorrectionWorkflowError):
                transition_correction(
                    lambda: connection, auth("gestor"), CORRECTION, target, "   "
                )
        with self.assertRaises(CorrectionWorkflowError):
            normalize_justification("x" * 1001)

    def test_final_state_and_manager_after_forward_are_conflicts(self):
        for role, state, target in (
            ("gestor", "aprovada", "rejeitada"),
            ("gestor", "encaminhada_rh", "aprovada"),
            ("funcionario", "encaminhada_rh", "cancelada"),
        ):
            connection = Connection([row(state)])
            with self.subTest(role=role, state=state), self.assertRaises(CorrectionWorkflowError) as raised:
                transition_correction(
                    lambda: connection,
                    auth(role),
                    CORRECTION,
                    target,
                    "Justificativa" if target == "rejeitada" else None,
                    own=role == "funcionario",
                )
            self.assertEqual(raised.exception.status, 409)

    def test_rejected_and_cancelled_never_touch_original_or_effective_view(self):
        for target, own in (("rejeitada", False), ("cancelada", True)):
            role = "gestor" if not own else "funcionario"
            observation = "Nao procede" if target == "rejeitada" else None
            _, connection = run_transition(
                role, "pendente_gestor", target, observation, own=own
            )
            sql = " ".join(call[0] for call in connection.cursor_value.calls)
            self.assertNotIn("UPDATE marcacoes", sql)
        effective = (Path(__file__).parents[1] / "services/effective_timekeeping.py").read_text(encoding="utf-8")
        self.assertIn("c.estado = 'aprovada'", effective)

    def test_web_exposes_new_states_timeline_and_valid_actions(self):
        root = Path(__file__).parents[1]
        template = (root / "templates/ocorrencias.html").read_text(encoding="utf-8")
        javascript = (root / "static/js/ocorrencias.js").read_text(encoding="utf-8")
        self.assertIn("encaminhada_rh", template)
        self.assertIn("encaminhar-rh", javascript)
        self.assertIn("acoes_permitidas", javascript)
        self.assertIn("historico", javascript)


if __name__ == "__main__":
    unittest.main()
