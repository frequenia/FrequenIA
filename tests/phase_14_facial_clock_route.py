import os
import unittest

from flask import Flask


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "phase-14-test-jwt-key")

from routes.views import criar_marcacao_facial


class FacialClockTransactionTests(unittest.TestCase):
    def test_authenticated_facial_clock_route_is_active_and_validates_payload(self):
        app = Flask(__name__)
        with app.test_request_context(
            "/api/marcacoes/facial",
            method="POST",
            json={
                "tipo": "entrada",
                "tentativa_facial_id": "00000000-0000-0000-0000-000000000010",
                "empresa_id": "nao-permitida",
            },
        ):
            response, status = criar_marcacao_facial.__wrapped__()

        self.assertEqual(status, 400)
        self.assertIn("identificadores", response.get_json()["erro"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
