import math
import threading
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from services import face_service


class FakeDeepFace:
    build_count = 0
    lock = threading.Lock()

    @classmethod
    def build_model(cls, model_name):
        with cls.lock:
            cls.build_count += 1
        return object()

    @staticmethod
    def extract_faces(**kwargs):
        return [{"face": np.ones((112, 112, 3), dtype=np.float32)}]

    @staticmethod
    def represent(**kwargs):
        return [{"embedding": [1.0] * 512}]


class MultipleFacesDeepFace(FakeDeepFace):
    @staticmethod
    def extract_faces(**kwargs):
        face = {"face": np.ones((112, 112, 3), dtype=np.float32)}
        return [face, face]


class NoFaceDeepFace(FakeDeepFace):
    @staticmethod
    def extract_faces(**kwargs):
        raise ValueError("face could not be detected")


class InvalidEmbeddingDeepFace(FakeDeepFace):
    @staticmethod
    def represent(**kwargs):
        return [{"embedding": [float("nan")] * 512}]


def synthetic_png():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    encoded, buffer = cv2.imencode(".png", image)
    if not encoded:
        raise AssertionError("could not create the controlled test image")
    return buffer.tobytes()


class BiometricFaceServiceTests(unittest.TestCase):
    def setUp(self):
        face_service._reset_for_tests()
        FakeDeepFace.build_count = 0

    def tearDown(self):
        face_service._reset_for_tests()

    def test_valid_image_generates_normalized_512_vector(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=FakeDeepFace
        ):
            embedding = face_service.generate_biometric_embedding(synthetic_png())

        self.assertEqual(len(embedding), 512)
        self.assertTrue(all(math.isfinite(value) for value in embedding))
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in embedding)), 1.0, places=6
        )
        self.assertEqual(FakeDeepFace.build_count, 1)

    def test_invalid_binary_is_rejected_before_face_processing(self):
        with self.assertRaises(face_service.InvalidFaceImageError):
            face_service.generate_biometric_embedding(b"not-an-image")
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_more_than_one_face_is_rejected(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=MultipleFacesDeepFace
        ):
            with self.assertRaises(face_service.InvalidFaceCountError):
                face_service.generate_biometric_embedding(synthetic_png())
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_missing_face_is_rejected(self):
        with patch.object(
            face_service, "_load_deepface_class", return_value=NoFaceDeepFace
        ):
            with self.assertRaises(face_service.InvalidFaceCountError):
                face_service.generate_biometric_embedding(synthetic_png())
        self.assertFalse(face_service.is_arcface_model_loaded())

    def test_non_finite_embedding_is_rejected(self):
        with patch.object(
            face_service,
            "_load_deepface_class",
            return_value=InvalidEmbeddingDeepFace,
        ):
            with self.assertRaises(face_service.InvalidFaceImageError):
                face_service.generate_biometric_embedding(synthetic_png())

    def test_cosine_match_uses_server_threshold(self):
        reference = [1.0] + ([0.0] * 511)
        same = [1.0] + ([0.0] * 511)
        different = [0.0, 1.0] + ([0.0] * 510)

        self.assertAlmostEqual(face_service.cosine_distance(reference, same), 0.0)
        self.assertAlmostEqual(face_service.cosine_distance(reference, different), 1.0)
        self.assertTrue(face_service.verify_face_match(reference, same, 0.68))
        self.assertFalse(face_service.verify_face_match(reference, different, 0.68))

    def test_average_embedding_normalizes_each_vector_and_final_result(self):
        first = [2.0] + ([0.0] * 511)
        second = [0.0, 4.0] + ([0.0] * 510)
        average = face_service.calcular_embedding_medio([first, second])

        self.assertEqual(len(average), 512)
        self.assertTrue(all(math.isfinite(value) for value in average))
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in average)), 1.0)
        self.assertAlmostEqual(average[0], 1.0 / math.sqrt(2), places=6)
        self.assertAlmostEqual(average[1], 1.0 / math.sqrt(2), places=6)

    def test_average_embedding_rejects_invalid_vectors(self):
        valid = [1.0] + ([0.0] * 511)
        for invalid in (
            [],
            [[1.0]],
            [[float("nan")] + ([0.0] * 511)],
            [[float("inf")] + ([0.0] * 511)],
            [[0.0] * 512],
            [valid, [-1.0] + ([0.0] * 511)],
        ):
            with self.subTest(invalid_type=str(invalid)[:30]):
                with self.assertRaises(face_service.InvalidFaceImageError):
                    face_service.calcular_embedding_medio(invalid)

    def test_cosine_comparison_rejects_invalid_vectors_and_threshold(self):
        valid = [1.0] + ([0.0] * 511)
        with self.assertRaises(ValueError):
            face_service.cosine_distance(valid, [1.0])
        with self.assertRaises(ValueError):
            face_service.verify_face_match(valid, valid, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
