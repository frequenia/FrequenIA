import math
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import cv2
import numpy as np

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-13-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-13-test-jwt-key")

from services import face_service


def synthetic_png():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    encoded, buffer = cv2.imencode(".png", image)
    if not encoded:
        raise AssertionError("could not create controlled image")
    return buffer.tobytes()


class LiveDeepFace:
    calls = 0
    lock = threading.Lock()

    @classmethod
    def extract_faces(cls, **kwargs):
        with cls.lock:
            cls.calls += 1
        if kwargs.get("anti_spoofing") is not True:
            raise AssertionError("anti_spoofing must be enabled")
        return [
            {
                "face": np.ones((112, 112, 3), dtype=np.float32),
                "is_real": True,
                "antispoof_score": 0.97,
            }
        ]


class SpoofDeepFace(LiveDeepFace):
    @classmethod
    def extract_faces(cls, **kwargs):
        result = super().extract_faces(**kwargs)
        result[0]["is_real"] = False
        result[0]["antispoof_score"] = 0.94
        return result


class BrokenLivenessDeepFace(LiveDeepFace):
    @classmethod
    def extract_faces(cls, **kwargs):
        raise RuntimeError("controlled liveness failure")


class MultipleFacesDeepFace(LiveDeepFace):
    @classmethod
    def extract_faces(cls, **kwargs):
        face = super().extract_faces(**kwargs)[0]
        return [face, dict(face)]


class NoFaceDeepFace(LiveDeepFace):
    @classmethod
    def extract_faces(cls, **kwargs):
        raise ValueError("face could not be detected")


class PassiveLivenessTests(unittest.TestCase):
    def setUp(self):
        face_service._reset_for_tests()
        LiveDeepFace.calls = 0

    def tearDown(self):
        face_service._reset_for_tests()

    def test_live_image_is_approved_before_arcface(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=LiveDeepFace
        ):
            approved, score = face_service.verify_passive_liveness(synthetic_png())

        self.assertTrue(approved)
        self.assertTrue(math.isclose(score, 0.97))
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_spoof_is_rejected_before_arcface(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=SpoofDeepFace
        ):
            approved, score = face_service.verify_passive_liveness(synthetic_png())

        self.assertFalse(approved)
        self.assertTrue(math.isclose(score, 0.94))
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_concurrent_first_use_is_initialized_once(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=LiveDeepFace
        ):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        lambda _: face_service.verify_passive_liveness(synthetic_png()),
                        range(4),
                    )
                )

        self.assertTrue(all(approved for approved, _score in results))
        self.assertEqual(LiveDeepFace.calls, 4)
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_technical_failure_is_controlled(self):
        with patch.object(
            face_service,
            "_load_deepface_class",
            return_value=BrokenLivenessDeepFace,
        ):
            with self.assertRaises(face_service.LivenessServiceUnavailableError):
                face_service.verify_passive_liveness(synthetic_png())

        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_multiple_faces_are_rejected_before_arcface(self):
        with patch.object(
            face_service,
            "_load_deepface_class",
            return_value=MultipleFacesDeepFace,
        ):
            with self.assertRaises(face_service.InvalidFaceCountError):
                face_service.verify_passive_liveness(synthetic_png())

        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_missing_face_is_rejected_before_arcface(self):
        with patch.object(
            face_service,
            "_load_deepface_class",
            return_value=NoFaceDeepFace,
        ):
            with self.assertRaises(face_service.InvalidFaceCountError):
                face_service.verify_passive_liveness(synthetic_png())

        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_invalid_binary_is_rejected_without_liveness_model(self):
        with patch.object(face_service, "_load_deepface_class") as loader:
            with self.assertRaises(face_service.InvalidFaceImageError):
                face_service.verify_passive_liveness(b"not-an-image")

        loader.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
