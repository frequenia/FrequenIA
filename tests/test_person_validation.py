import unittest
from unittest.mock import patch
from flask import Flask, g, session
from utils.person_validation import PersonValidationError, validate_person_contact
from routes.views import cadastrar_usuario, atualizar_usuario, cadastrar_empresa, logout


class PersonValidationTests(unittest.TestCase):
    def test_menu_logout_revokes_session_and_returns_to_login(self):
        app = Flask(__name__)
        app.secret_key = 'synthetic-test-only'
        with app.test_request_context('/logout'):
            session['auth_session_id'] = 'synthetic-session'
            session['user_id'] = 'synthetic-user'
            with patch('routes.views.revogar_familia_por_sessao') as revoke, patch('routes.views.limpar_cookie_refresh', side_effect=lambda response: response):
                response = logout()
            revoke.assert_called_once_with('synthetic-session')
            self.assertEqual(dict(session), {})
            self.assertTrue(response.location.endswith('/login-page'))

    def test_accepts_names_with_accents_and_common_punctuation(self):
        for name in ['João da Silva', 'Ana-Maria', "D’Ávila", "O'Connor", 'João Jr.', '李 明', 'Jose\u0301']:
            self.assertTrue(validate_person_contact(name, '')[0])

    def test_rejects_digits_in_any_script_and_non_name_content(self):
        for name in ['João2', 'Ana １２', 'João²', 'Maria١', '<script>', '---', '', 'A' * 161]:
            with self.subTest(name=name), self.assertRaises(PersonValidationError):
                validate_person_contact(name, '')

    def test_accepts_national_fixed_and_mobile_formats(self):
        for phone in ['1132345678', '(11) 3234-5678', '11987654321', '(11) 98765-4321', '', None]:
            validate_person_contact('Pessoa Sintética', phone)

    def test_rejects_incomplete_long_or_non_national_phones(self):
        for phone in ['119999999', '119999999999', '+55 11 98765-4321', '11abc32345678', '11876543210', '01987654321', '11          32345678']:
            with self.subTest(phone=phone), self.assertRaises(PersonValidationError):
                validate_person_contact('Pessoa Sintética', phone)

    def test_collects_both_field_errors(self):
        with self.assertRaises(PersonValidationError) as caught:
            validate_person_contact('Pessoa2', '123', prefix='administrador.')
        self.assertEqual(set(caught.exception.fields), {'administrador.nome', 'administrador.telefone'})

    def test_routes_reject_before_database_and_identify_fields(self):
        app = Flask(__name__)
        payload = {'nome': 'Pessoa2', 'telefone': '123', 'funcionario_id': '11111111-1111-4111-8111-111111111111'}
        for handler in [cadastrar_usuario, atualizar_usuario]:
            with self.subTest(route=handler.__name__), app.test_request_context('/', method='POST', json=payload):
                with patch('routes.views.conectar_bd') as connect:
                    response, status = handler.__wrapped__()
                self.assertEqual(status, 400)
                self.assertEqual(set(response.get_json()['campos']), {'nome', 'telefone'})
                connect.assert_not_called()
        company = {'razao': 'Empresa 123', 'cnpj': '11111111111111', 'administrador': {'nome': 'Pessoa2', 'telefone': '123'}}
        with app.test_request_context('/', method='POST', json=company):
            g.auth_context = {'user_id': 'synthetic'}
            with patch('routes.views.conectar_bd') as connect:
                response, status = cadastrar_empresa.__wrapped__()
            self.assertEqual(status, 400)
            self.assertIn('administrador.nome', response.get_json()['campos'])
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
