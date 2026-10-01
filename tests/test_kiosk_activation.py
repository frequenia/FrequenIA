"""Ativação do computador e administração de terminais sem acesso real ao banco."""

import os
import unittest
from unittest.mock import patch

from flask import Flask, g, session

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "kiosk-test-jwt-key")

from routes.kiosk import (
    activation_page,
    activate_terminal,
    kiosk_bp,
    kiosk_page,
    list_terminals,
    provision_terminal,
)
from utils.terminal_auth import terminal_required

TERMINAL = "00000000-0000-0000-0000-000000000004"
COMPANY = "00000000-0000-0000-0000-000000000001"


class Cursor:
    def __init__(self, rows=(), all_rows=()):
        self.rows = list(rows)
        self.all_rows = list(all_rows)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return self.all_rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def cursor(self, **_kwargs):
        return self.cursor_value

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


class KioskActivationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="../templates")
        self.app.secret_key = "test"
        self.app.register_blueprint(kiosk_bp)

    def test_unactivated_or_revoked_page_goes_to_activation(self):
        with self.app.test_request_context("/quiosque/ponto"):
            response = kiosk_page()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, "/quiosque/ativar")
        with self.app.test_request_context("/quiosque/ponto"):
            session["terminal_ponto_id"] = TERMINAL
            with patch("utils.terminal_auth.conectar_bd", return_value=Connection(Cursor())):
                response = kiosk_page()
            self.assertEqual(response.status_code, 302)
            self.assertNotIn("terminal_ponto_id", session)

    def test_api_still_rejects_unactivated_terminal(self):
        protected = terminal_required(lambda: "ok")
        with self.app.test_request_context("/api/quiosque/marcacoes/facial", method="POST"):
            response, status = protected()
            self.assertEqual(status, 401)
            self.assertEqual(response.get_json()["erro"], "Terminal não autenticado.")

    def test_activation_uses_credential_hash_and_session_cookie(self):
        credential = "valid-test-credential-which-is-long-enough"
        cursor = Cursor(rows=[(TERMINAL,)])
        with self.app.test_request_context(
            "/api/quiosque/ativar", method="POST", json={"credencial": credential}
        ):
            session["user_id"] = "prior-admin"
            with patch("routes.kiosk.conectar_bd", return_value=Connection(cursor)):
                response = activate_terminal()
            self.assertEqual(response.status_code, 204)
            self.assertEqual(session["terminal_ponto_id"], TERMINAL)
            self.assertTrue(session.permanent)
            self.assertNotIn("user_id", session)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertNotIn(credential, str(cursor.calls))
            self.assertIn("credencial_hash=%s", cursor.calls[0][0])

    def test_invalid_credential_does_not_activate(self):
        with self.app.test_request_context(
            "/api/quiosque/ativar", method="POST", json={"credencial": "too-short"}
        ):
            response, status = activate_terminal()
            self.assertEqual(status, 401)
            self.assertNotIn("terminal_ponto_id", session)
        with self.app.test_request_context(
            "/api/quiosque/ativar", method="POST", json={"credencial": "a" * 40}
        ):
            with patch("routes.kiosk.conectar_bd", return_value=Connection(Cursor())):
                response, status = activate_terminal()
            self.assertEqual(status, 401)
            self.assertNotIn("terminal_ponto_id", session)

    def test_active_terminal_is_redirected_to_recognition(self):
        with self.app.test_request_context("/quiosque/ativar"):
            session["terminal_ponto_id"] = TERMINAL
            with patch("routes.kiosk.conectar_bd", return_value=Connection(Cursor(rows=[(1,)]))):
                response = activation_page()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, "/quiosque/ponto")

    def test_activation_page_renders_without_a_terminal_or_credentials(self):
        response = self.app.test_client().get("/quiosque/ativar")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="activation-form"', response.data)
        self.assertIn(b'/static/js/ativarTerminal.js', response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_admin_terminal_list_is_scoped_to_company(self):
        cursor = Cursor(all_rows=[])
        with self.app.test_request_context("/api/admin/terminais-ponto"):
            g.auth_context = {"empresa_id": COMPANY}
            with patch("routes.kiosk.conectar_bd", return_value=Connection(cursor)):
                response = list_terminals.__wrapped__()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(cursor.calls[0][1], (COMPANY,))
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_provisioned_secret_is_once_only_and_company_scoped(self):
        from datetime import datetime, timezone
        cursor = Cursor(rows=[{
            "id": TERMINAL,
            "nome": "Recepção",
            "status": "ativo",
            "created_at": datetime.now(timezone.utc),
        }])
        with self.app.test_request_context(
            "/api/admin/terminais-ponto", method="POST", json={"nome": " Recepção "}
        ):
            g.auth_context = {"empresa_id": COMPANY}
            with patch("routes.kiosk.conectar_bd", return_value=Connection(cursor)):
                response, status = provision_terminal.__wrapped__()
            self.assertEqual(status, 201)
            self.assertEqual(response.get_json()["terminal"]["nome"], "Recepção")
            self.assertGreaterEqual(len(response.get_json()["terminal"]["credencial"]), 32)
            self.assertEqual(cursor.calls[0][1][0:2], (COMPANY, "Recepção"))
            self.assertNotIn(response.get_json()["terminal"]["credencial"], str(cursor.calls))


if __name__ == "__main__":
    unittest.main()
