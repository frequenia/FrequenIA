import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from flask import Flask, jsonify

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "mobile-notifications-test-jwt-key")

from routes.views import views_bp


COMPANY_A = "00000000-0000-0000-0000-000000000101"
COMPANY_B = "00000000-0000-0000-0000-000000000102"
EMPLOYEE_A = "00000000-0000-0000-0000-000000000103"
USER_A = "00000000-0000-0000-0000-000000000104"
USER_B = "00000000-0000-0000-0000-000000000105"
NOTICE_A = "00000000-0000-0000-0000-000000000106"
CREATED_AT = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
READ_AT = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row

    def close(self):
        pass


class Connection:
    def __init__(self, rows=None, row=None):
        self.test_cursor = Cursor(rows=rows, row=row)
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


class MobileNotificationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(views_bp)
        self.client = self.app.test_client()
        self.context = {
            "user_id": USER_A,
            "funcionario_id": EMPLOYEE_A,
            "empresa_id": COMPANY_A,
            "session_id": "00000000-0000-0000-0000-000000000107",
            "familia_id": "00000000-0000-0000-0000-000000000108",
            "perfil": "funcionario",
        }

    def authenticated(self, method, path, connection):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(self.context, None),
        ), patch("routes.views.conectar_bd", return_value=connection):
            return self.client.open(
                path,
                method=method,
                headers={"Authorization": "Bearer fixture"},
            )

    def test_authentication_is_required_without_opening_database(self):
        with patch("routes.views.conectar_bd") as connect:
            list_response = self.client.get("/api/notificacoes")
            read_response = self.client.post(f"/api/notificacoes/{NOTICE_A}/ler")
        self.assertEqual(list_response.status_code, 401)
        self.assertEqual(read_response.status_code, 401)
        connect.assert_not_called()

    def test_listing_contract_uses_only_session_user_and_company(self):
        connection = Connection(rows=[{
            "id": UUID(NOTICE_A),
            "tipo": "ocorrencia_aprovada",
            "titulo": "Solicitação aprovada",
            "mensagem": "Sua solicitação foi aprovada.",
            "created_at": CREATED_AT,
            "read_at": None,
        }])
        response = self.authenticated(
            "GET",
            f"/api/notificacoes?usuario_id={USER_B}&empresa_id={COMPANY_B}",
            connection,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(connection.test_cursor.params, (USER_A, COMPANY_A))
        self.assertIn("usuario_id=%s", connection.test_cursor.sql)
        self.assertIn("empresa_id=%s", connection.test_cursor.sql)
        self.assertEqual(response.json, {"notificacoes": [{
            "id": NOTICE_A,
            "tipo": "ocorrencia_aprovada",
            "titulo": "Solicitação aprovada",
            "mensagem": "Sua solicitação foi aprovada.",
            "created_at": "2026-09-24T12:00:00+00:00",
            "read_at": None,
        }]})

    def test_same_company_other_user_cannot_change_listing_authority(self):
        connection = Connection(rows=[])
        response = self.authenticated(
            "GET", f"/api/notificacoes?usuario_id={USER_B}", connection
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"notificacoes": []})
        self.assertEqual(connection.test_cursor.params, (USER_A, COMPANY_A))

    def test_cross_tenant_query_cannot_change_listing_authority(self):
        connection = Connection(rows=[])
        response = self.authenticated(
            "GET", f"/api/notificacoes?empresa_id={COMPANY_B}", connection
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(connection.test_cursor.params, (USER_A, COMPANY_A))

    def test_owner_can_mark_notification_as_read(self):
        connection = Connection(row={"id": UUID(NOTICE_A), "read_at": READ_AT})
        response = self.authenticated(
            "POST", f"/api/notificacoes/{NOTICE_A}/ler", connection
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            "id": NOTICE_A,
            "read_at": "2026-09-24T13:00:00+00:00",
        })
        identifier, user_id, company_id = connection.test_cursor.params
        self.assertEqual(str(identifier), NOTICE_A)
        self.assertEqual((user_id, company_id), (USER_A, COMPANY_A))
        self.assertIn("usuario_id=%s", connection.test_cursor.sql)
        self.assertIn("empresa_id=%s", connection.test_cursor.sql)
        self.assertEqual(connection.commits, 1)

    def test_other_user_notification_is_not_found_and_not_changed(self):
        connection = Connection(row=None)
        response = self.authenticated(
            "POST", f"/api/notificacoes/{NOTICE_A}/ler", connection
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"erro": "Notificação não encontrada."})
        self.assertEqual(connection.test_cursor.params[1:], (USER_A, COMPANY_A))

    def test_cross_tenant_notification_has_same_non_disclosing_404(self):
        connection = Connection(row=None)
        response = self.authenticated(
            "POST", f"/api/notificacoes/{NOTICE_A}/ler", connection
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("empresa", response.get_data(as_text=True).lower())

    def test_invalid_notification_id_is_rejected_before_database_access(self):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(self.context, None),
        ), patch("routes.views.conectar_bd") as connect:
            response = self.client.post(
                "/api/notificacoes/not-a-uuid/ler",
                headers={"Authorization": "Bearer fixture"},
            )
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
