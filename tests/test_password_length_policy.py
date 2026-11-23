"""Limites de novas senhas, simbolos e compatibilidade do login existente."""
import unittest
from unittest.mock import patch

from flask import Flask
from routes.views import resetar_senha
from utils.password_policy import validate_new_password


class PasswordLengthPolicyTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def reset(self, password):
        with self.app.test_request_context('/auth/password/reset', method='POST',
                                          json={'new_password': password}):
            with patch('routes.views.conectar_bd') as connect:
                response, status = resetar_senha()
                connect.assert_not_called()
                return response.get_json(), status

    def test_rejects_short_long_and_non_text_passwords(self):
        for password in ('Aa1!xxx', 'Aa1!' + 'x' * 61, 12345678):
            with self.subTest(password_type=type(password).__name__):
                body, status = self.reset(password)
                self.assertEqual(status, 400)
                self.assertIn('8 e 64', body['erro'])

    def test_accepts_boundaries_and_allowed_symbols_before_token_validation(self):
        for password in ('Aa1?xxxx', 'Aa1?' + 'x' * 60):
            with self.subTest(length=len(password)):
                body, status = self.reset(password)
                self.assertEqual(status, 400)  # Sem token; nunca altera uma senha.
                self.assertNotIn('8 e 64', body['erro'])

    def test_all_listed_symbols_accepted(self):
        for symbol in '.+-[]*~_#:?@':
            validate_new_password('Aa1' + symbol + 'xxxx')

    def test_spaces_unlisted_symbols_and_missing_categories_rejected(self):
        for password in ('Aa1? xxx', ' Aa1?xxx', 'Aa1?xxx ', 'Aa1?\txxx',
                         'Aa1!xxxx', 'Aa1$xxxx', 'Aa1é?xxx',
                         'aa1?xxxx', 'AA1?XXXX', 'Aaa?xxxx', 'Aa11xxxx'):
            with self.subTest(password=password):
                with self.assertRaises(ValueError):
                    validate_new_password(password)
