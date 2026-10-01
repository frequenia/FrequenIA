import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from flask import Flask, render_template

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "facial-failure-admin-ui-test-key")

from routes.occurrences import occurrences_bp


COMPANY_A = "00000000-0000-0000-0000-000000000201"
COMPANY_B = "00000000-0000-0000-0000-000000000202"
MANAGER = "00000000-0000-0000-0000-000000000203"
EMPLOYEE = "00000000-0000-0000-0000-000000000204"
OCCURRENCE = "00000000-0000-0000-0000-000000000205"
UNIT = "00000000-0000-0000-0000-000000000206"
TEAM = "00000000-0000-0000-0000-000000000207"
FIRST_AT = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def auth(role="gestor", company=COMPANY_A):
    return {
        "user_id": "00000000-0000-0000-0000-000000000208",
        "funcionario_id": MANAGER,
        "empresa_id": company,
        "session_id": "00000000-0000-0000-0000-000000000209",
        "familia_id": "00000000-0000-0000-0000-000000000210",
        "perfil": role,
    }


def occurrence_row(**overrides):
    row = {
        "id": UUID(OCCURRENCE),
        "funcionario_id": UUID(EMPLOYEE),
        "funcionario": "Maria Piloto",
        "matricula": "MAT-22",
        "unidade_id": UUID(UNIT),
        "unidade": "Unidade Centro",
        "equipe_id": UUID(TEAM),
        "equipe": "Equipe Azul",
        "primeira_ocorrencia_at": FIRST_AT,
        "estado": "aberta",
        "descricao": "Ocorrência automática após cinco falhas faciais válidas.",
        "created_at": CREATED_AT,
        "resolved_at": None,
        "decisao": None,
        "responsavel": None,
    }
    row.update(overrides)
    return row


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class Connection:
    def __init__(self, cursor):
        self.test_cursor = cursor

    def cursor(self, **_kwargs):
        return self.test_cursor

    def close(self):
        pass


class FacialFailureAdminUITests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.root = root
        self.app = Flask(
            __name__,
            template_folder=str(root / "templates"),
            static_folder=str(root / "static"),
        )
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(occurrences_bp)
        self.client = self.app.test_client()

    def request_as(self, path, role="gestor", company=COMPANY_A, connection=None):
        patches = [
            patch(
                "utils.auth_decorator._load_persistent_authentication",
                return_value=(auth(role, company), None),
            )
        ]
        if connection is not None:
            patches.append(patch("routes.occurrences.conectar_bd", return_value=connection))
        with patches[0]:
            if len(patches) == 1:
                return self.client.get(path, headers={"Authorization": "Bearer test"})
            with patches[1]:
                return self.client.get(path, headers={"Authorization": "Bearer test"})

    def test_page_and_navigation_are_management_only(self):
        for role in ("gestor", "rh", "administrador"):
            with self.subTest(role=role):
                self.assertEqual(
                    self.request_as("/ocorrencias/falhas-faciais", role).status_code,
                    200,
                )
        self.assertEqual(
            self.request_as("/ocorrencias/falhas-faciais", "funcionario").status_code,
            403,
        )
        with self.app.test_request_context():
            admin_menu = render_template("menu.html", tipo="gestor", nome="Gestor")
            employee_menu = render_template("menu.html", tipo="funcionario", nome="Pessoa")
        self.assertIn('/ocorrencias/falhas-faciais', admin_menu)
        self.assertNotIn('/ocorrencias/falhas-faciais', employee_menu)

    def test_list_contract_has_organizational_context_without_biometrics(self):
        cursor = Cursor(rows=[occurrence_row()])
        response = self.request_as(
            "/api/gestao/ocorrencias/falhas-faciais",
            connection=Connection(cursor),
        )
        self.assertEqual(response.status_code, 200)
        item = response.json["ocorrencias"][0]
        self.assertEqual(item["funcionario"], "Maria Piloto")
        self.assertEqual(item["matricula"], "MAT-22")
        self.assertEqual(item["unidade"], "Unidade Centro")
        self.assertEqual(item["equipe"], "Equipe Azul")
        self.assertEqual(item["primeira_ocorrencia_at"], FIRST_AT.isoformat())
        for forbidden in ("imagem", "embedding", "score", "credencial"):
            self.assertNotIn(forbidden, item)

    def test_filters_are_parameterized_and_keep_manager_scope_and_tenant(self):
        cursor = Cursor(rows=[])
        response = self.request_as(
            "/api/gestao/ocorrencias/falhas-faciais"
            f"?estado=aberta&busca=Maria&unidade_id={UNIT}&equipe_id={TEAM}"
            "&inicio=2026-09-01&fim=2026-09-30",
            connection=Connection(cursor),
        )
        self.assertEqual(response.status_code, 200)
        sql, params = cursor.calls[0]
        self.assertIn("gestores_escopos", sql)
        self.assertIn("u.nome ILIKE %s OR f.matricula ILIKE %s", sql)
        self.assertEqual(params[0], COMPANY_A)
        for expected in (MANAGER, "aberta", UNIT, TEAM, "%Maria%"):
            self.assertIn(expected, params)
        self.assertNotIn(COMPANY_B, params)

    def test_invalid_filters_are_400_without_database_access(self):
        for query in ("estado=inexistente", "inicio=2026-10-02&fim=2026-10-01", "empresa_id=" + COMPANY_B):
            with self.subTest(query=query), patch(
                "utils.auth_decorator._load_persistent_authentication",
                return_value=(auth(), None),
            ), patch("routes.occurrences.conectar_bd") as connect:
                response = self.client.get(
                    "/api/gestao/ocorrencias/falhas-faciais?" + query,
                    headers={"Authorization": "Bearer test"},
                )
            self.assertEqual(response.status_code, 400)
            connect.assert_not_called()

    def test_detail_contains_origin_decision_and_sanitized_audit(self):
        audit = [{
            "acao": "ocorrencia.falha_facial_automatica",
            "ocorrido_at": CREATED_AT,
            "metadados": {"quantidade_tentativas": 5},
            "ator": None,
        }]
        cursor = Cursor(row=occurrence_row(), rows=audit)
        response = self.request_as(
            f"/api/gestao/ocorrencias/falhas-faciais/{OCCURRENCE}",
            connection=Connection(cursor),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["origem"], "automatica_falha_facial")
        self.assertIsNone(response.json["decisao"])
        self.assertEqual(response.json["auditoria"][0]["acao"], audit[0]["acao"])
        self.assertNotIn("metadados", response.json["auditoria"][0])
        self.assertEqual(len(cursor.calls), 2)
        self.assertEqual(cursor.calls[1][1], (COMPANY_A, OCCURRENCE))

    def test_out_of_scope_and_cross_tenant_detail_use_same_404(self):
        for company in (COMPANY_A, COMPANY_B):
            cursor = Cursor(row=None)
            response = self.request_as(
                f"/api/gestao/ocorrencias/falhas-faciais/{OCCURRENCE}",
                company=company,
                connection=Connection(cursor),
            )
            self.assertEqual(response.status_code, 404)
            sql, params = cursor.calls[0]
            self.assertIn("gestores_escopos", sql)
            self.assertEqual(params[1], company)
            self.assertNotIn("empresa", response.get_data(as_text=True).lower())

    def test_admin_and_hr_remain_limited_to_session_company(self):
        for role in ("rh", "administrador"):
            cursor = Cursor(rows=[])
            response = self.request_as(
                "/api/gestao/ocorrencias/falhas-faciais",
                role=role,
                connection=Connection(cursor),
            )
            self.assertEqual(response.status_code, 200)
            sql, params = cursor.calls[0]
            self.assertNotIn("gestores_escopos", sql)
            self.assertEqual(params[0], COMPANY_A)

    def test_common_employee_cannot_use_management_api(self):
        with patch("routes.occurrences.conectar_bd") as connect:
            response = self.request_as(
                "/api/gestao/ocorrencias/falhas-faciais", "funcionario"
            )
        self.assertEqual(response.status_code, 403)
        connect.assert_not_called()

    def test_interface_handles_required_states_without_sensitive_fields(self):
        template = (self.root / "templates" / "falhasFaciais.html").read_text(encoding="utf-8")
        script = (self.root / "static" / "js" / "falhasFaciais.js").read_text(encoding="utf-8")
        for expected in (
            "Carregando",
            "Nenhuma ocorrência",
            "Nenhum resultado",
            "Sessão expirada",
            "page-error",
            "Iniciar análise",
            "Justificativa",
            "window.confirm",
            "error.status === 409",
        ):
            self.assertIn(expected, template + script)
        for forbidden in ("embedding", "score", "imagem facial", "credencial"):
            self.assertNotIn(forbidden, (template + script).lower())


if __name__ == "__main__":
    unittest.main()
