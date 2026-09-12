import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask, g


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-14-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-14-test-jwt-key")

from routes.views import criar_marcacao_facial


class FacialClockTransactionTests(unittest.TestCase):
    def test_insert_failure_rolls_back_without_success(self):
        app = Flask(__name__)
        app.config["FACIAL_ATTEMPT_MAX_AGE_SECONDS"] = 120
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            None,
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "resultado": "sucesso",
                "motivo_codigo": "match",
                "dentro_da_janela": True,
            },
            None,
            None,
        ]

        def execute(sql, params=None):
            if "INSERT INTO marcacoes" in sql:
                raise RuntimeError("controlled insert failure")

        cursor.execute.side_effect = execute
        payload = {
            "tipo": "entrada",
            "tentativa_facial_id": "00000000-0000-0000-0000-000000000010",
        }
        headers = {"Idempotency-Key": "00000000-0000-0000-0000-000000000020"}

        with app.test_request_context(
            "/api/marcacoes/facial", method="POST", json=payload, headers=headers
        ):
            g.auth_context = {
                "empresa_id": "00000000-0000-0000-0000-000000000030"
            }
            g.auth_funcionario_id = "00000000-0000-0000-0000-000000000040"
            with patch("routes.views.conectar_bd", return_value=connection):
                response, status = criar_marcacao_facial.__wrapped__()

        self.assertEqual(status, 500)
        self.assertEqual(
            response.get_json(), {"erro": "Não foi possível processar a marcação."}
        )
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        cursor.close.assert_called_once_with()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
