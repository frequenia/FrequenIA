import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db


class DatabaseTlsTests(unittest.TestCase):
    def test_production_uses_verify_full_and_the_configured_ca(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "supabase.crt"
            certificate.write_text("test certificate", encoding="utf-8")
            environment = {
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql://example.invalid/postgres",
                "DATABASE_SSLROOTCERT": str(certificate),
            }
            sentinel = object()
            with patch.dict(os.environ, environment, clear=True), patch(
                "db.psycopg2.connect", return_value=sentinel
            ) as connect:
                self.assertIs(db.conectar_bd(), sentinel)

            _, kwargs = connect.call_args
            self.assertEqual(kwargs["sslmode"], "verify-full")
            self.assertEqual(kwargs["sslrootcert"], str(certificate))

    def test_development_keeps_encrypted_connections_without_a_ca_file(self):
        environment = {
            "APP_ENV": "development",
            "DATABASE_URL": "postgresql://example.invalid/postgres",
        }
        with patch.dict(os.environ, environment, clear=True), patch(
            "db.psycopg2.connect", return_value=object()
        ) as connect:
            db.conectar_bd()

        _, kwargs = connect.call_args
        self.assertEqual(kwargs["sslmode"], "require")
        self.assertNotIn("sslrootcert", kwargs)

    def test_verifying_mode_fails_closed_without_a_readable_ca(self):
        environment = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://example.invalid/postgres",
            "DATABASE_SSLROOTCERT": "missing-supabase-ca.crt",
        }
        with patch.dict(os.environ, environment, clear=True), self.assertRaisesRegex(
            RuntimeError, "readable certificate"
        ):
            db.conectar_bd()

    def test_unknown_ssl_mode_is_rejected(self):
        environment = {
            "DATABASE_URL": "postgresql://example.invalid/postgres",
            "DATABASE_SSLMODE": "unsafe-mode",
        }
        with patch.dict(os.environ, environment, clear=True), self.assertRaisesRegex(
            RuntimeError, "unsupported"
        ):
            db.conectar_bd()


if __name__ == "__main__":
    unittest.main(verbosity=2)
