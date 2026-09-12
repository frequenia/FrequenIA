import inspect
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask, g, session


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "hotfix-14c1-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "hotfix-14c1-test-jwt-key")

from routes.views import listar_usuarios_select


COMPANY_ID = "00000000-0000-0000-0000-000000000001"
EMPLOYEE_WITHOUT_BIOMETRIC = "00000000-0000-0000-0000-000000000002"
EMPLOYEE_WITH_BIOMETRIC = "00000000-0000-0000-0000-000000000003"
AUTH_SESSION_ID = "00000000-0000-0000-0000-000000000004"
USER_ID = "00000000-0000-0000-0000-000000000005"


class WebBiometricHotfixTests(unittest.TestCase):
    def _auth_context(self, role):
        return {
            "session_id": AUTH_SESSION_ID,
            "familia_id": "00000000-0000-0000-0000-000000000006",
            "user_id": USER_ID,
            "funcionario_id": EMPLOYEE_WITHOUT_BIOMETRIC,
            "empresa_id": COMPANY_ID,
            "perfil": role,
        }

    def test_listing_uses_employee_id_company_and_biometrics(self):
        app = Flask(__name__)
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [
            {
                "funcionario_id": EMPLOYEE_WITHOUT_BIOMETRIC,
                "nome": "Funcionario Sem Biometria",
                "possui_biometria_ativa": False,
            },
            {
                "funcionario_id": EMPLOYEE_WITH_BIOMETRIC,
                "nome": "Funcionario Com Biometria",
                "possui_biometria_ativa": True,
            },
        ]

        with app.test_request_context("/listar_usuarios_select"):
            g.auth_context = {"empresa_id": COMPANY_ID}
            with patch("routes.views.conectar_bd", return_value=connection):
                response = listar_usuarios_select.__wrapped__()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            [
                {
                    "funcionario_id": EMPLOYEE_WITHOUT_BIOMETRIC,
                    "nome": "Funcionario Sem Biometria",
                    "possui_biometria_ativa": False,
                },
                {
                    "funcionario_id": EMPLOYEE_WITH_BIOMETRIC,
                    "nome": "Funcionario Com Biometria",
                    "possui_biometria_ativa": True,
                },
            ],
        )
        sql, params = cursor.execute.call_args.args
        self.assertIn("FROM funcionarios f", sql)
        self.assertIn("FROM biometrias b", sql)
        self.assertIn("b.funcionario_id = f.id", sql)
        self.assertIn("b.empresa_id = f.empresa_id", sql)
        self.assertIn("f.empresa_id = %s", sql)
        self.assertNotIn("FROM fotos", sql)
        self.assertEqual(params, (COMPANY_ID,))
        cursor.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_frontend_uses_employee_id_and_official_endpoint(self):
        with open("static/js/cadastrarFoto.js", encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("option.value = funcionario.funcionario_id", source)
        self.assertIn(
            "/api/admin/funcionarios/${encodeURIComponent(funcionarioCapturaId)}/biometria",
            source,
        )
        self.assertIn('formData.append("imagem"', source)
        self.assertNotIn('fetch("/iniciar_cadastro"', source)
        self.assertNotIn('fetch("/adicionar_foto"', source)
        self.assertNotIn('fetch("/finalizar_cadastro"', source)
        self.assertNotIn("JSON.stringify({ nome", source)

    def test_corrected_listing_has_admin_role_decorator(self):
        source = inspect.getsource(listar_usuarios_select)
        self.assertIn('@require_roles("administrador")', source)

    def test_listing_rejects_unauthenticated_request(self):
        app = Flask(__name__)
        app.secret_key = "hotfix-14c1-request-test"
        with app.test_request_context("/listar_usuarios_select"):
            response, status = listar_usuarios_select()

        self.assertEqual(status, 401)
        self.assertEqual(response.get_json()["erro"], "Autenticação necessária.")

    def test_listing_rejects_non_administrator(self):
        app = Flask(__name__)
        app.secret_key = "hotfix-14c1-request-test"
        with app.test_request_context("/listar_usuarios_select"):
            session["user_id"] = USER_ID
            session["funcionario_id"] = EMPLOYEE_WITHOUT_BIOMETRIC
            session["auth_session_id"] = AUTH_SESSION_ID
            with patch(
                "utils.auth_decorator.buscar_sessao_access",
                return_value=self._auth_context("funcionario"),
            ):
                response, status = listar_usuarios_select()

        self.assertEqual(status, 403)
        self.assertEqual(response.get_json()["erro"], "Acesso não autorizado.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
