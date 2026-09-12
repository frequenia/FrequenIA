import os
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-9a-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-9a-test-jwt-key")

from services import face_service


class FakeDeepFace:
    build_count = 0
    count_lock = threading.Lock()
    model = object()

    @classmethod
    def build_model(cls, model_name):
        self = cls
        time.sleep(0.02)
        with self.count_lock:
            self.build_count += 1
        return self.model

    @staticmethod
    def extract_faces(**kwargs):
        return []

    @staticmethod
    def represent(**kwargs):
        return [{"embedding": [1.0] * 512}]


class FaceServiceTests(unittest.TestCase):
    def setUp(self):
        face_service._reset_for_tests()
        FakeDeepFace.build_count = 0

    def tearDown(self):
        face_service._reset_for_tests()

    def test_first_access_loads_and_second_access_reuses_model(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=FakeDeepFace
        ):
            first = face_service.get_arcface_model()
            second = face_service.get_arcface_model()

        self.assertIs(first, FakeDeepFace.model)
        self.assertIs(first, second)
        self.assertEqual(FakeDeepFace.build_count, 1)
        self.assertTrue(face_service.is_arcface_model_loaded())

    def test_concurrent_access_builds_only_one_model(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=FakeDeepFace
        ):
            with ThreadPoolExecutor(max_workers=8) as executor:
                models = list(
                    executor.map(lambda _: face_service.get_arcface_model(), range(8))
                )

        self.assertEqual(FakeDeepFace.build_count, 1)
        self.assertTrue(all(model is FakeDeepFace.model for model in models))

    def test_load_failure_is_controlled_and_does_not_publish_partial_model(self):
        with patch.object(
            face_service,
            "_load_deepface_class",
            side_effect=RuntimeError("simulated model failure"),
        ):
            with self.assertLogs("services.face_service", level="ERROR"):
                with self.assertRaises(face_service.FaceServiceUnavailableError):
                    face_service.get_arcface_model()

        self.assertFalse(face_service.is_arcface_model_loaded())


class ApplicationArchitectureTests(unittest.TestCase):
    def test_app_import_and_health_do_not_import_deepface_or_build_arcface(self):
        project_root = Path(__file__).resolve().parents[1]
        code = """
import os
import sys
os.environ['APP_ENV'] = 'development'
os.environ['FLASK_SECRET_KEY'] = 'phase-9a-subprocess-flask-key'
os.environ['JWT_SECRET_KEY'] = 'phase-9a-subprocess-jwt-key'
import app
from services.face_service import is_arcface_model_loaded
assert 'deepface' not in sys.modules
assert not is_arcface_model_loaded()
response = app.app.test_client().get('/health')
assert response.status_code == 200
assert response.get_json() == {'status': 'ok'}
assert 'deepface' not in sys.modules
assert not is_arcface_model_loaded()
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_model_failure_returns_503_and_health_remains_available(self):
        import app
        import routes.face as legacy_face

        class FakeCursor:
            def close(self):
                pass

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def rollback(self):
                pass

            def close(self):
                pass

        with (
            patch.object(legacy_face, "conectar_bd", return_value=FakeConnection()),
            patch.object(legacy_face, "register_vector"),
            patch.object(
                legacy_face,
                "reconhecer_uma_imagem",
                side_effect=face_service.FaceServiceUnavailableError(),
            ),
        ):
            client = app.app.test_client()
            facial_response = client.post("/reconhecer", json={"imagem": "fake"})
            health_response = client.get("/health")

        self.assertEqual(facial_response.status_code, 503)
        self.assertEqual(
            facial_response.get_json(),
            {"erro": "Servico facial temporariamente indisponivel."},
        )
        self.assertEqual(health_response.status_code, 200)

    def test_legacy_clock_write_is_explicitly_disabled(self):
        import app

        response = app.app.test_client().post(
            "/confirmar_ponto", json={"usuario_id": "arbitrary"}
        )
        self.assertEqual(response.status_code, 410)
        self.assertIn("desativado", response.get_json()["erro"])

    def test_legacy_face_module_no_longer_contains_clock_writes(self):
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "routes" / "face.py").read_text(encoding="utf-8")
        self.assertNotIn("INSERT INTO ponto", source)
        self.assertNotIn("INSERT INTO presenca", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
