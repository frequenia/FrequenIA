import os
import unittest
from unittest.mock import patch

from flask import Flask, jsonify

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "mobile-profile-test-jwt-key")

from routes.views import views_bp


COMPANY = "00000000-0000-0000-0000-000000000001"
EMPLOYEE = "00000000-0000-0000-0000-000000000002"
USER = "00000000-0000-0000-0000-000000000003"


class Cursor:
    def __init__(self, row):
        self.row = row
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row

    def close(self):
        pass


class Connection:
    def __init__(self, row):
        self.test_cursor = Cursor(row)

    def cursor(self, **_kwargs):
        return self.test_cursor

    def close(self):
        pass


class MobileProfileTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(views_bp)
        self.client = self.app.test_client()
        self.context = {
            "user_id": USER,
            "funcionario_id": EMPLOYEE,
            "empresa_id": COMPANY,
            "session_id": "00000000-0000-0000-0000-000000000004",
            "familia_id": "00000000-0000-0000-0000-000000000005",
            "perfil": "funcionario",
        }

    def request(self, row, query=""):
        connection = Connection(row)
        with patch("utils.auth_decorator._load_persistent_authentication", return_value=(self.context, None)), patch(
            "routes.views.conectar_bd", return_value=connection
        ):
            response = self.client.get(
                "/api/perfil" + query, headers={"Authorization": "Bearer fixture"}
            )
        return response, connection.test_cursor

    def test_profile_contains_only_readable_own_data_and_masked_cpf(self):
        row = {
            "nome": "Pessoa Teste", "cpf": "12345678912", "telefone": "11999999999",
            "email": "teste@example.invalid", "matricula": "M-17",
            "perfil": "funcionario", "empresa_nome": "Empresa A",
            "unidade_nome": "Piloto", "equipe_nome": "TI", "cargo_nome": "Analista",
            "senha_hash": "never-send", "embedding": "never-send",
        }
        response, cursor = self.request(
            row, "?user_id=outro&funcionario_id=outro&empresa_id=outra"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["nome"], "Pessoa Teste")
        self.assertEqual(response.json["cpf_mascarado"], "***.***.***-12")
        self.assertEqual(response.json["empresa"], "Empresa A")
        self.assertEqual(cursor.params, (EMPLOYEE, COMPANY, USER))
        self.assertIn("f.empresa_id = %s", cursor.sql)
        self.assertIn("WHERE u.id = %s", cursor.sql)
        self.assertNotIn("12345678912", response.get_data(as_text=True))
        for forbidden in ("senha_hash", "embedding", "token", "user_id", "empresa_id"):
            self.assertNotIn(forbidden, response.json)

    def test_optional_fields_remain_null_for_neutral_mobile_display(self):
        row = {
            "nome": "Pessoa Teste", "cpf": "12345678912", "telefone": None,
            "email": None, "matricula": "M-17", "perfil": "funcionario",
            "empresa_nome": "Empresa A", "unidade_nome": "Piloto",
            "equipe_nome": None, "cargo_nome": None,
        }
        response, _ = self.request(row)
        self.assertEqual(response.status_code, 200)
        for field in ("telefone", "email", "equipe", "cargo"):
            self.assertIsNone(response.json[field])

    def test_missing_or_foreign_link_returns_same_404(self):
        response, cursor = self.request(None, "?empresa_id=foreign")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(cursor.params, (EMPLOYEE, COMPANY, USER))

    def test_missing_and_revoked_session_return_401_without_query(self):
        self.assertEqual(self.client.get("/api/perfil").status_code, 401)
        with patch("utils.auth_decorator._load_persistent_authentication") as auth, patch(
            "routes.views.conectar_bd"
        ) as connect:
            auth.side_effect = lambda: (None, (jsonify({"erro": "Sessão revogada."}), 401))
            response = self.client.get(
                "/api/perfil", headers={"Authorization": "Bearer revoked"}
            )
            self.assertEqual(response.status_code, 401)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
