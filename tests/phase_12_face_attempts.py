import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "phase-12-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "phase-12-test-jwt-key")

import routes.biometrics as biometric_routes
from services.face_service import compare_face_embeddings


class FaceAttemptPersistenceTests(unittest.TestCase):
    def test_comparison_returns_decision_and_distance(self):
        reference = [1.0] + ([0.0] * 511)
        same = [1.0] + ([0.0] * 511)
        different = [0.0, 1.0] + ([0.0] * 510)

        self.assertEqual(compare_face_embeddings(reference, same, 0.68), (True, 0.0))
        self.assertEqual(
            compare_face_embeddings(reference, different, 0.68),
            (False, 1.0),
        )

    def test_attempt_uses_database_clock_and_commits(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ["attempt-id"]
        with patch("routes.biometrics.conectar_bd", return_value=connection):
            attempt_id = biometric_routes._record_face_attempt(
                "employee-id", "company-id", "sucesso", "match", 0.12
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("INSERT INTO tentativas_faciais", sql)
        self.assertIn("clock_timestamp()", sql)
        self.assertNotIn("imagem", sql.lower())
        self.assertNotIn("embedding", sql.lower())
        self.assertIn("RETURNING id", sql)
        self.assertEqual(attempt_id, "attempt-id")
        self.assertEqual(
            params,
            ("company-id", "employee-id", "sucesso", "match", 0.12),
        )
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once_with()

    def test_attempt_rolls_back_when_insert_fails(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = RuntimeError("controlled database failure")
        with (
            patch("routes.biometrics.conectar_bd", return_value=connection),
            self.assertRaises(RuntimeError),
        ):
            biometric_routes._record_face_attempt(
                "employee-id", "company-id", "falha", "nao_corresponde", 1.0
            )

        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
