import re
import unittest
from unittest.mock import MagicMock, patch

from services.employee_onboarding import (
    allocate_registration,
    cargo_registration_code,
    first_access_credentials,
)


class EmployeeOnboardingTest(unittest.TestCase):
    def test_role_code_uses_initials_without_accents(self):
        self.assertEqual(cargo_registration_code("Analista de Recursos Humanos"), "ARH")
        self.assertEqual(cargo_registration_code("Técnico 2"), "T2")

    def test_registration_is_role_scoped_and_zero_padded(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"nome": "Recursos Humanos", "codigo_matricula": "RH"},
            {"ultimo_numero": 12},
        ]
        self.assertEqual(allocate_registration(cursor, "empresa", "cargo"), "RH-000012")
        sequence_sql = cursor.execute.call_args_list[-1].args[0]
        self.assertIn("ON CONFLICT (empresa_id, cargo_id) DO UPDATE", sequence_sql)

    @patch("services.employee_onboarding.secrets.token_urlsafe")
    def test_first_access_password_is_not_the_email_token(self, token_urlsafe):
        token_urlsafe.side_effect = ["senha-interna-aleatoria", "token-do-email"]
        credentials = first_access_credentials()
        self.assertNotIn("senha-interna-aleatoria", credentials["password_hash"])
        self.assertEqual(credentials["raw_token"], "token-do-email")
        self.assertRegex(credentials["token_hash"], re.compile(r"^[0-9a-f]{64}$"))


if __name__ == "__main__":
    unittest.main()
