"""Guardas de configuração da chave Flask, sem usar o segredo histórico."""

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
IMPORT_CHECK = (
    "import dotenv; "
    "dotenv.load_dotenv = lambda *args, **kwargs: None; "
    "import app; "
    "print(app.app.test_client().get('/health').status_code)"
)


class FlaskSecretConfigurationTests(unittest.TestCase):
    def _import_with_key(self, flask_key=None, jwt_key="j" * 32, app_env="development"):
        environment = os.environ.copy()
        environment.pop("FLASK_SECRET_KEY", None)
        environment.pop("JWT_SECRET_KEY", None)
        environment.pop("PASSWORD_RESET_TEST_KEY", None)
        environment["APP_ENV"] = app_env
        environment["JWT_SECRET_KEY"] = jwt_key
        if flask_key is not None:
            environment["FLASK_SECRET_KEY"] = flask_key
        return subprocess.run(
            [sys.executable, "-c", IMPORT_CHECK],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_missing_key_has_no_fallback(self):
        result = self._import_with_key()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FLASK_SECRET_KEY", result.stderr)

    def test_example_placeholder_is_rejected(self):
        result = self._import_with_key("CHANGE_ME_WITH_A_RANDOM_SECRET")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FLASK_SECRET_KEY", result.stderr)

    def test_short_key_is_rejected(self):
        result = self._import_with_key("x" * 31)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FLASK_SECRET_KEY", result.stderr)

    def test_reused_jwt_key_is_rejected(self):
        result = self._import_with_key("j" * 32)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be different", result.stderr)

    def test_distinct_configured_key_starts_app(self):
        for app_env in ("development", "homologation", "production"):
            with self.subTest(app_env=app_env):
                result = self._import_with_key("x" * 32, app_env=app_env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "200")

    def test_current_app_does_not_assign_a_literal_secret(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        secret_assignments = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any("SECRET_KEY" in ast.unparse(target) or "secret_key" in ast.unparse(target)
                    for target in node.targets)
        ]
        self.assertTrue(secret_assignments)
        self.assertFalse(any(isinstance(node.value, ast.Constant) for node in secret_assignments))

    def test_cookie_signed_with_previous_test_key_is_not_accepted(self):
        with patch.dict(os.environ, {
            "APP_ENV": "development",
            "FLASK_SECRET_KEY": "x" * 32,
            "JWT_SECRET_KEY": "j" * 32,
        }):
            import app

        self.assertFalse(app.app.config.get("SECRET_KEY_FALLBACKS"))
        client = app.app.test_client()
        with patch.dict(app.app.config, {"SECRET_KEY": "a" * 32}):
            with client.session_transaction() as session:
                session.update({
                    "user_id": "00000000-0000-0000-0000-000000000001",
                    "funcionario_id": "00000000-0000-0000-0000-000000000002",
                    "auth_session_id": "00000000-0000-0000-0000-000000000003",
                })

        with (
            patch.dict(app.app.config, {"SECRET_KEY": "b" * 32}),
            patch("utils.auth_decorator.buscar_sessao_access") as session_lookup,
        ):
            response = client.get("/api/jornada")

        self.assertEqual(response.status_code, 401)
        session_lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
