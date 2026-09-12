import io
import math
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-15-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-15-test-jwt-key")

import app
from services.face_service import (
    FaceServiceUnavailableError,
    InvalidFaceCountError,
    LivenessServiceUnavailableError,
)


AUTH_CONTEXT = {
    "session_id": "00000000-0000-0000-0000-000000000001",
    "familia_id": "00000000-0000-0000-0000-000000000002",
    "user_id": "00000000-0000-0000-0000-000000000003",
    "funcionario_id": "00000000-0000-0000-0000-000000000004",
    "empresa_id": "00000000-0000-0000-0000-000000000005",
    "perfil": "administrador",
}
URL = f"/api/admin/funcionarios/{AUTH_CONTEXT['funcionario_id']}/biometria"
VECTOR = [1.0] + ([0.0] * 511)


def image_form(count, content=b"controlled-image", extension="png"):
    return {
        "imagem": [
            (io.BytesIO(content), f"face-{index}.{extension}")
            for index in range(count)
        ]
    }


class AverageEnrollmentRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = AUTH_CONTEXT["user_id"]
            session["funcionario_id"] = AUTH_CONTEXT["funcionario_id"]
            session["auth_session_id"] = AUTH_CONTEXT["session_id"]
        self.auth_patch = patch(
            "utils.auth_decorator.buscar_sessao_access",
            return_value=AUTH_CONTEXT,
        )
        self.auth_patch.start()

    def tearDown(self):
        self.auth_patch.stop()

    def _successful_enrollment(self, count):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {"id": AUTH_CONTEXT["funcionario_id"]},
            {
                "id": "00000000-0000-0000-0000-000000000006",
                "status": "ativa",
                "modelo": "ArcFace",
                "versao_modelo": "deepface-0.0.99",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "revoked_at": None,
            },
        ]
        cursor.rowcount = 0
        vectors = []
        for index in range(count):
            vector = [0.0] * 512
            vector[index] = 1.0
            vectors.append(vector)

        with (
            patch("routes.biometrics._employee_exists", return_value=True),
            patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)) as liveness,
            patch("routes.biometrics.generate_biometric_embedding", side_effect=vectors) as generate,
            patch("routes.biometrics.conectar_bd", return_value=connection),
            patch("routes.biometrics.register_vector"),
        ):
            response = self.client.post(URL, data=image_form(count))

        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        self.assertEqual(liveness.call_count, count)
        self.assertEqual(generate.call_count, count)
        insert_calls = [
            call for call in cursor.execute.call_args_list
            if "INSERT INTO biometrias" in call.args[0]
        ]
        self.assertEqual(len(insert_calls), 1)
        stored_embedding = insert_calls[0].args[1][2]
        self.assertEqual(len(stored_embedding), 512)
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in stored_embedding)), 1.0, places=6
        )
        connection.commit.assert_called_once_with()

    def test_three_images_create_one_average_embedding(self):
        self._successful_enrollment(3)

    def test_five_images_create_one_average_embedding(self):
        self._successful_enrollment(5)

    def test_rejects_fewer_than_three_images(self):
        with patch("routes.biometrics._employee_exists", return_value=True):
            response = self.client.post(URL, data=image_form(2))
        self.assertEqual(response.status_code, 400)

    def test_rejects_more_than_five_images(self):
        with patch("routes.biometrics._employee_exists", return_value=True):
            response = self.client.post(URL, data=image_form(6))
        self.assertEqual(response.status_code, 400)

    def test_invalid_image_rejects_entire_enrollment(self):
        with (
            patch("routes.biometrics._employee_exists", return_value=True),
            patch(
                "routes.biometrics.verify_passive_liveness",
                side_effect=InvalidFaceCountError("Imagem invalida."),
            ),
            patch("routes.biometrics.conectar_bd") as connect,
        ):
            response = self.client.post(URL, data=image_form(3))
        self.assertEqual(response.status_code, 422)
        connect.assert_not_called()

    def test_liveness_rejection_rejects_entire_enrollment(self):
        with (
            patch("routes.biometrics._employee_exists", return_value=True),
            patch("routes.biometrics.verify_passive_liveness", return_value=(False, 0.1)),
            patch("routes.biometrics.generate_biometric_embedding") as generate,
            patch("routes.biometrics.conectar_bd") as connect,
        ):
            response = self.client.post(URL, data=image_form(3))
        self.assertEqual(response.status_code, 422)
        generate.assert_not_called()
        connect.assert_not_called()

    def test_model_and_liveness_failures_return_503(self):
        for target, error in (
            ("routes.biometrics.generate_biometric_embedding", FaceServiceUnavailableError()),
            ("routes.biometrics.verify_passive_liveness", LivenessServiceUnavailableError()),
        ):
            with self.subTest(target=target):
                patches = [
                    patch("routes.biometrics._employee_exists", return_value=True),
                    patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
                    patch("routes.biometrics.generate_biometric_embedding", return_value=VECTOR),
                    patch(target, side_effect=error),
                ]
                started = [item.start() for item in patches]
                try:
                    response = self.client.post(URL, data=image_form(3))
                finally:
                    for item in reversed(patches):
                        item.stop()
                self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
