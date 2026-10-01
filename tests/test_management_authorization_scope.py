"""Cobertura de isolamento gestor -> unidade/equipe nas APIs de gestão."""

import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "manager-scope-test-jwt-key")

from routes.occurrences import occurrences_bp
from routes.timekeeping import timekeeping_bp
from services.management_scope import employee_scope_clause

COMPANY_A = "00000000-0000-0000-0000-000000000001"
COMPANY_B = "00000000-0000-0000-0000-000000000002"
MANAGER = "00000000-0000-0000-0000-000000000010"
EMPLOYEE_TEAM_A = "00000000-0000-0000-0000-000000000011"
EMPLOYEE_TEAM_B = "00000000-0000-0000-0000-000000000012"
EMPLOYEE_OTHER_COMPANY = "00000000-0000-0000-0000-000000000013"


def auth(role="gestor", company=COMPANY_A):
    return {
        "user_id": "00000000-0000-0000-0000-000000000020",
        "funcionario_id": MANAGER,
        "empresa_id": company,
        "session_id": "00000000-0000-0000-0000-000000000021",
        "familia_id": "00000000-0000-0000-0000-000000000022",
        "perfil": role,
    }


class ScopePolicyTests(unittest.TestCase):
    def test_manager_scope_combines_session_company_and_team_or_unit_assignment(self):
        clause, params = employee_scope_clause(auth())
        normalized = " ".join(clause.split())
        self.assertIn("FROM gestores_escopos ge", normalized)
        self.assertIn("ge.empresa_id = f.empresa_id", normalized)
        self.assertIn("ge.unidade_id = f.unidade_id", normalized)
        self.assertIn("ge.equipe_id IS NULL OR ge.equipe_id = f.equipe_id", normalized)
        self.assertEqual(params, (MANAGER,))

    def test_admin_and_hr_keep_company_wide_policy(self):
        for role in ("administrador", "rh"):
            with self.subTest(role=role):
                self.assertEqual(employee_scope_clause(auth(role)), ("TRUE", ()))


class ManagementRouteScopeTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.app = Flask(__name__, template_folder=str(root / "templates"))
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(timekeeping_bp)
        self.app.register_blueprint(occurrences_bp)
        self.client = self.app.test_client()

    def request_as(self, path, role="gestor", company=COMPANY_A):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth(role, company), None),
        ):
            return self.client.get(path, headers={"Authorization": "Bearer test"})

    def post_as(self, path, role="gestor", company=COMPANY_A, body=None):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth(role, company), None),
        ):
            return self.client.post(
                path, headers={"Authorization": "Bearer test"}, json=body or {}
            )

    def test_manager_can_query_authorized_team_member(self):
        employee = {"funcionario_id": EMPLOYEE_TEAM_A, "nome": "Equipe A", "matricula": "A"}
        with patch("routes.timekeeping._load_management_records", return_value=(employee, [])) as loader:
            response = self.request_as(f"/api/gestao/pontos?funcionario_id={EMPLOYEE_TEAM_A}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loader.call_args.args[0]["perfil"], "gestor")

    def test_manager_is_denied_other_team_and_other_company_for_points_and_export(self):
        for employee_id in (EMPLOYEE_TEAM_B, EMPLOYEE_OTHER_COMPANY):
            with self.subTest(employee_id=employee_id), patch(
                "routes.timekeeping._load_management_records", return_value=(None, [])
            ):
                points = self.request_as(f"/api/gestao/pontos?funcionario_id={employee_id}")
                export = self.request_as(f"/exportar-pontos?formato=csv&funcionario_id={employee_id}")
            self.assertEqual(points.status_code, 404)
            self.assertEqual(export.status_code, 404)

    def test_manager_list_and_occurrence_detail_queries_use_scope(self):
        connection = MagicMock(); cursor = MagicMock()
        connection.cursor.return_value = cursor; cursor.fetchall.return_value = []
        with patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.request_as("/api/gestao/ocorrencias")
        self.assertEqual(response.status_code, 200)
        query, params = cursor.execute.call_args.args
        self.assertIn("gestores_escopos", query)
        self.assertEqual(params[0], COMPANY_A)
        self.assertIn(MANAGER, params)

        connection = MagicMock(); cursor = MagicMock()
        connection.cursor.return_value = cursor; cursor.fetchone.return_value = None
        with patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.request_as(f"/api/gestao/ocorrencias/{EMPLOYEE_TEAM_B}")
        self.assertEqual(response.status_code, 404)
        query, params = cursor.execute.call_args.args
        self.assertIn("gestores_escopos", query)
        self.assertIn(MANAGER, params)

    def test_manager_cannot_decide_correction_outside_scope(self):
        connection = MagicMock(); cursor = MagicMock()
        connection.cursor.return_value = cursor; cursor.fetchone.return_value = None
        correction_id = "00000000-0000-0000-0000-000000000099"
        with patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.post_as(
                f"/api/gestao/ocorrencias/{correction_id}/aprovar",
                body={"observacao": "Teste autorizado"},
            )
        self.assertEqual(response.status_code, 404)
        query, params = cursor.execute.call_args.args
        self.assertIn("FOR UPDATE OF c", query)
        self.assertIn("gestores_escopos", query)
        self.assertIn(MANAGER, params)

    def test_regular_employee_keeps_forbidden_status(self):
        self.assertEqual(self.request_as("/api/gestao/funcionarios", "funcionario").status_code, 403)
        self.assertEqual(self.request_as("/api/gestao/ocorrencias", "funcionario").status_code, 403)

    def test_facial_failure_occurrences_keep_management_scope_and_404(self):
        connection = MagicMock(); cursor = MagicMock()
        connection.cursor.return_value = cursor; cursor.fetchall.return_value = []
        with patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.request_as("/api/gestao/ocorrencias/falhas-faciais")
        self.assertEqual(response.status_code, 200)
        query, params = cursor.execute.call_args.args
        self.assertIn("gestores_escopos", query)
        self.assertIn(MANAGER, params)

        connection = MagicMock(); cursor = MagicMock()
        connection.cursor.return_value = cursor; cursor.fetchone.return_value = None
        occurrence_id = "00000000-0000-0000-0000-000000000099"
        with patch("routes.occurrences.conectar_bd", return_value=connection):
            response = self.request_as(f"/api/gestao/ocorrencias/falhas-faciais/{occurrence_id}")
        self.assertEqual(response.status_code, 404)
        query, params = cursor.execute.call_args.args
        self.assertIn("gestores_escopos", query)
        self.assertIn(MANAGER, params)
