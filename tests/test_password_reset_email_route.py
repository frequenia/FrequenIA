import hashlib
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from routes.views import views_bp


class PasswordResetEmailRouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-only",
            PASSWORD_RESET_TOKEN_MINUTES=30,
            PASSWORD_RESET_TEST_KEY="controlled-test-key",
        )
        self.app.register_blueprint(views_bp)
        self.client = self.app.test_client()

    def _connection_with_user(self, user):
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = user
        connection.cursor.return_value = cursor
        return connection, cursor

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.conectar_bd")
    def test_public_request_sends_email_but_never_returns_raw_token(self, connect, send):
        connection, cursor = self._connection_with_user(
            {
                "id": "user-id",
                "email": "pessoa@example.com",
                "senha_hash": "existing-hash",
                "status": "ativo",
            }
        )
        connect.return_value = connection

        response = self.client.post(
            "/auth/password/forgot",
            json={"identifier": "pessoa@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.get_json())
        send.assert_called_once()
        recipient, raw_token, expires_in = send.call_args.args
        self.assertEqual(recipient, "pessoa@example.com")
        self.assertEqual(expires_in, 30)

        insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO password_reset_tokens" in call.args[0]
        )
        stored_hash = insert_call.args[1][1]
        self.assertEqual(stored_hash, hashlib.sha256(raw_token.encode()).hexdigest())
        self.assertNotEqual(stored_hash, raw_token)

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.conectar_bd")
    def test_unknown_account_keeps_same_public_response_and_sends_nothing(
        self, connect, send
    ):
        connection, _ = self._connection_with_user(None)
        connect.return_value = connection

        missing = self.client.post(
            "/auth/password/forgot",
            json={"identifier": "inexistente@example.com"},
        )

        self.assertEqual(missing.status_code, 200)
        self.assertNotIn("token", missing.get_json())
        send.assert_not_called()

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.conectar_bd")
    def test_controlled_test_hook_bypasses_real_delivery(self, connect, send):
        connection, _ = self._connection_with_user(
            {
                "id": "user-id",
                "email": "pessoa@example.com",
                "senha_hash": "existing-hash",
                "status": "ativo",
            }
        )
        connect.return_value = connection

        response = self.client.post(
            "/auth/password/forgot",
            json={"identifier": "pessoa@example.com"},
            headers={"X-Password-Reset-Test-Key": "controlled-test-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json().get("test_token"))
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
