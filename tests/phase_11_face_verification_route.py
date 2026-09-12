import io
import inspect
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-11-route-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-11-route-test-jwt-key")

import app
import routes.biometrics as biometric_routes
from services.face_service import (
    FaceServiceUnavailableError,
    InvalidFaceCountError,
    InvalidFaceImageError,
)

MATCH_VECTOR = [1.0] + ([0.0] * 511)
OTHER_VECTOR = [0.0, 1.0] + ([0.0] * 510)
AUTH_CONTEXT = {
    "session_id": "00000000-0000-0000-0000-000000000001",
    "familia_id": "00000000-0000-0000-0000-000000000002",
    "user_id": "00000000-0000-0000-0000-000000000003",
    "funcionario_id": "00000000-0000-0000-0000-000000000004",
    "empresa_id": "00000000-0000-0000-0000-000000000005",
    "perfil": "funcionario",
}


def image_form(**extra):
    data = {"imagem": (io.BytesIO(b"controlled-test-image"), "face.png", "image/png")}
    data.update(extra)
    return data


class FaceVerificationRouteTests(unittest.TestCase):
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
        self.liveness_patch = patch(
            "routes.biometrics.verify_passive_liveness",
            return_value=(True, 0.99),
        )
        self.liveness_patch.start()

    def tearDown(self):
        self.liveness_patch.stop()
        self.auth_patch.stop()

    def post(self, **extra):
        return self.client.post("/api/biometria/verificar", data=image_form(**extra))

    def test_positive_match(self):
        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ) as active,
            patch(
                "routes.biometrics.generate_biometric_embedding",
                return_value=MATCH_VECTOR,
            ),
            patch(
                "routes.biometrics._record_face_attempt",
                return_value="00000000-0000-0000-0000-000000000001",
            ) as record_attempt,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "verificado": True,
                "motivo": "match",
                "tentativa_facial_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        active.assert_called_once_with(
            AUTH_CONTEXT["funcionario_id"], AUTH_CONTEXT["empresa_id"]
        )
        record_attempt.assert_called_once_with(
            AUTH_CONTEXT["funcionario_id"],
            AUTH_CONTEXT["empresa_id"],
            "sucesso",
            "match",
            0.0,
        )

    def test_negative_match(self):
        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ),
            patch(
                "routes.biometrics.generate_biometric_embedding",
                return_value=OTHER_VECTOR,
            ),
            patch("routes.biometrics._record_face_attempt") as record_attempt,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"verificado": False, "motivo": "nao_corresponde"},
        )
        record_attempt.assert_called_once_with(
            AUTH_CONTEXT["funcionario_id"],
            AUTH_CONTEXT["empresa_id"],
            "falha",
            "nao_corresponde",
            1.0,
        )

    def test_missing_biometric_does_not_process_image(self):
        with (
            patch("routes.biometrics._active_biometric", return_value=None),
            patch("routes.biometrics.generate_biometric_embedding") as generate,
            patch("routes.biometrics._record_face_attempt") as record_attempt,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json(),
            {"verificado": False, "motivo": "biometria_ausente"},
        )
        generate.assert_not_called()
        record_attempt.assert_called_once_with(
            AUTH_CONTEXT["funcionario_id"],
            AUTH_CONTEXT["empresa_id"],
            "falha",
            "biometria_ausente",
        )

    def test_client_cannot_control_identity_or_threshold(self):
        with patch(
            "routes.biometrics._active_biometric",
            return_value={"embedding": MATCH_VECTOR},
        ):
            identity = self.post(funcionario_id="arbitrary")
            threshold = self.post(threshold="2")
            liveness = self.post(liveness_ok="true")

        self.assertEqual(identity.status_code, 400)
        self.assertEqual(threshold.status_code, 400)
        self.assertEqual(liveness.status_code, 400)

    def test_liveness_rejection_stops_arcface_and_persists_failure(self):
        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ),
            patch(
                "routes.biometrics.verify_passive_liveness",
                return_value=(False, 0.91),
            ),
            patch("routes.biometrics.generate_biometric_embedding") as generate,
            patch("routes.biometrics.compare_face_embeddings") as compare,
            patch("routes.biometrics._record_face_attempt") as record_attempt,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"verificado": False, "motivo": "liveness_reprovado"},
        )
        generate.assert_not_called()
        compare.assert_not_called()
        record_attempt.assert_called_once_with(
            AUTH_CONTEXT["funcionario_id"],
            AUTH_CONTEXT["empresa_id"],
            "falha",
            "liveness_reprovado",
        )

    def test_liveness_service_failure_is_controlled(self):
        from services.face_service import LivenessServiceUnavailableError

        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ),
            patch(
                "routes.biometrics.verify_passive_liveness",
                side_effect=LivenessServiceUnavailableError(),
            ),
            patch("routes.biometrics.generate_biometric_embedding") as generate,
            patch("routes.biometrics._record_face_attempt") as record_attempt,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 503)
        generate.assert_not_called()
        record_attempt.assert_not_called()
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_controlled_face_errors(self):
        errors = (
            (InvalidFaceImageError("imagem invalida"), 400),
            (InvalidFaceCountError("quantidade invalida"), 422),
            (FaceServiceUnavailableError(), 503),
        )
        for error, expected_status in errors:
            with self.subTest(expected_status=expected_status):
                with (
                    patch(
                        "routes.biometrics._active_biometric",
                        return_value={"embedding": MATCH_VECTOR},
                    ),
                    patch(
                        "routes.biometrics.generate_biometric_embedding",
                        side_effect=error,
                    ),
                    patch("routes.biometrics._record_face_attempt") as record_attempt,
                ):
                    response = self.post()
                self.assertEqual(response.status_code, expected_status)
                record_attempt.assert_not_called()
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_persistence_failure_is_not_reported_as_success(self):
        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ),
            patch(
                "routes.biometrics.generate_biometric_embedding",
                return_value=MATCH_VECTOR,
            ),
            patch(
                "routes.biometrics._record_face_attempt",
                side_effect=RuntimeError("controlled persistence failure"),
            ),
        ):
            with self.assertLogs("routes.biometrics", level="ERROR"):
                response = self.post()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {"erro": "Nao foi possivel verificar a biometria."},
        )

    def test_missing_image_does_not_create_attempt(self):
        with (
            patch(
                "routes.biometrics._active_biometric",
                return_value={"embedding": MATCH_VECTOR},
            ),
            patch("routes.biometrics._record_face_attempt") as record_attempt,
        ):
            response = self.client.post("/api/biometria/verificar")

        self.assertEqual(response.status_code, 400)
        record_attempt.assert_not_called()

    def test_unauthenticated_request_is_rejected(self):
        self.auth_patch.stop()
        self.auth_patch = patch(
            "utils.auth_decorator.buscar_sessao_access", return_value=None
        )
        self.auth_patch.start()
        response = app.app.test_client().post("/api/biometria/verificar")
        self.assertEqual(response.status_code, 401)

    def test_active_biometric_query_is_strictly_one_to_one(self):
        source = inspect.getsource(biometric_routes._active_biometric)
        for required_filter in (
            "empresa_id = %s",
            "funcionario_id = %s",
            "status = 'ativa'",
        ):
            self.assertIn(required_filter, source)
        self.assertNotIn("<=>", source)
        self.assertNotIn("<->", source)
        self.assertNotIn("FROM fotos", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
