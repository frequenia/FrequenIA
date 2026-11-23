"""Listagem de unidades usada pelas configuracoes e cadastro de funcionarios."""
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask, g
from routes.views import listar_unidades

COMPANY = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class UnitListingSessionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_configuration_without_company_uses_authenticated_company(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = []
        with self.app.test_request_context('/listar_unidades'):
            g.auth_context = {'empresa_id': COMPANY}
            with patch('routes.views.conectar_bd', return_value=connection):
                response = listar_unidades.__wrapped__()
            self.assertEqual(response.get_json(), [])
        sql, params = connection.cursor.return_value.execute.call_args.args
        self.assertEqual(params, (COMPANY,))
        self.assertIn("status = 'ativa'", sql)
        connection.close.assert_called_once()

    def test_employee_registration_accepts_explicit_same_company(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = []
        with self.app.test_request_context('/listar_unidades?empresa_id=' + COMPANY):
            g.auth_context = {'empresa_id': COMPANY}
            with patch('routes.views.conectar_bd', return_value=connection):
                response = listar_unidades.__wrapped__()
            self.assertEqual(response.status_code, 200)
        self.assertEqual(connection.cursor.return_value.execute.call_args.args[1], (COMPANY,))

    def test_foreign_company_rejected_before_database_lookup(self):
        with self.app.test_request_context('/listar_unidades?empresa_id=' + OTHER):
            g.auth_context = {'empresa_id': COMPANY}
            with patch('routes.views.conectar_bd') as connect:
                _, status = listar_unidades.__wrapped__()
            self.assertEqual(status, 403)
            connect.assert_not_called()
