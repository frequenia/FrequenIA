from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, jsonify
from routes.units import units_bp
from services.unit_onboarding import UnitValidationError, validate_unit_payload

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
UNIT = '33333333-3333-4333-8333-333333333333'
TEAM = '44444444-4444-4444-8444-444444444444'
ACTOR = '55555555-5555-4555-8555-555555555555'


def context(role='administrador', company=A):
    return dict(user_id=ACTOR, empresa_id=company, perfil=role,
                funcionario_id=ACTOR, session_id='synthetic', familia_id='synthetic')


class UnitsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        self.app.register_blueprint(units_bp)
        self.client = self.app.test_client()
        self.payload = dict(nome='Filial 2', codigo=' fil_2 ', timezone='America/Sao_Paulo', equipe_nome='Equipe 2')

    def call(self, path='/api/admin/unidades', *, method='post', payload=None, role='administrador', company=A, connection=None):
        with patch('utils.auth_decorator._load_persistent_authentication', return_value=(context(role, company), None)), patch('routes.units.conectar_bd', return_value=connection) as connect:
            response = getattr(self.client, method)(path, json=payload)
        return response, connect

    def test_canonical_code_default_team_and_timezone(self):
        data = validate_unit_payload({'nome':' Filial   2 ', 'codigo':' fil_2 '})
        self.assertEqual(data, dict(nome='Filial 2', codigo='FIL_2', equipe_nome='Geral', timezone='America/Sao_Paulo'))

    def test_validation_collects_fields_and_rejects_tenant_and_unknown_keys(self):
        with self.assertRaises(UnitValidationError) as error:
            validate_unit_payload(dict(nome='', codigo='é', timezone='invalid/zone', equipe_nome=''))
        self.assertEqual(set(error.exception.fields), {'nome','codigo','timezone','equipe_nome'})
        for invalid in [None, [], {'nome':'X','codigo':'X','empresa_id':B}, {'nome':'X','codigo':'X','ativa':True}]:
            response, connect = self.call(payload=invalid)
            self.assertEqual(response.status_code, 400)
            connect.assert_not_called()

    def test_field_limits_and_bad_timezone(self):
        for key, value in [('nome','X'*161), ('equipe_nome','X'*161), ('codigo','X'*41), ('codigo','abc def'), ('timezone',''), ('nome','X\x00Y')]:
            with self.subTest(key=key), self.assertRaises(UnitValidationError):
                validate_unit_payload(dict(self.payload, **{key:value}))

    def test_only_company_admin_can_access_page_and_endpoints(self):
        for role in ['rh','gestor','funcionario','administrador_geral']:
            for path, method in [('/admin/unidades','get'),('/api/admin/unidades','get'),('/api/admin/unidades','post')]:
                with self.subTest(role=role, path=path, method=method):
                    response, connect = self.call(path, method=method, payload=self.payload, role=role)
                    self.assertEqual(response.status_code, 403)
                    connect.assert_not_called()
        response, _ = self.call('/admin/unidades', method='get')
        self.assertEqual(response.status_code, 200)

    def test_missing_session_cannot_create_or_list(self):
        with self.app.app_context():
            missing = (jsonify(erro='Autenticação necessária.'), 401)
        with patch('utils.auth_decorator._load_persistent_authentication', return_value=(None, missing)), patch('routes.units.conectar_bd') as connect:
            self.assertEqual(self.client.get('/api/admin/unidades').status_code, 401)
            self.assertEqual(self.client.post('/api/admin/unidades',json=self.payload).status_code, 401)
            connect.assert_not_called()

    def test_list_uses_authenticated_company_and_rejects_query_tenant(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        response, _ = self.call(method='get', company=B, connection=connection)
        self.assertEqual(response.get_json(), {'unidades':[]})
        self.assertEqual(cursor.execute.call_args.args[1], (B,))
        self.assertIn('WHERE empresa_id=%s', cursor.execute.call_args.args[0])
        connection.close.assert_called_once()
        for method in ['get','post']:
            response, connect = self.call('/api/admin/unidades?empresa_id='+A, method=method, payload=self.payload)
            self.assertEqual(response.status_code, 400)
            connect.assert_not_called()

    def test_creation_commits_team_and_audits_in_same_company_with_mobile_disabled(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [dict(id=UNIT,nome='Filial 2',codigo='FIL_2',timezone='America/Sao_Paulo',status='ativa',marcacao_mobile_ativa=False),dict(id=TEAM,nome='Equipe 2')]
        response, _ = self.call(payload=self.payload, company=B, connection=connection)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()['unidade']['marcacao_mobile_ativa'])
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call.args[1][0] == B for call in calls))
        self.assertIn("'ativa',false", calls[0].args[0])
        self.assertEqual(calls[1].args[1], (B,UNIT,'Equipe 2'))
        self.assertTrue(all(call.args[1][1] == ACTOR for call in calls[2:]))
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once()

    def test_audit_failure_rolls_back_and_does_not_return_partial_success(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [dict(id=UNIT,codigo='FIL_2',timezone='America/Sao_Paulo'),dict(id=TEAM,nome='Equipe 2')]
        cursor.execute.side_effect = [None,None,None,RuntimeError('synthetic audit failure')]
        response, _ = self.call(payload=self.payload, connection=connection)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('unidade',response.get_json())
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        connection.close.assert_called_once()

    def test_duplicate_constraint_has_field_error_and_rolls_back(self):
        class Conflict(Exception):
            def __init__(self, name): self.diag = MagicMock(constraint_name=name)
        for key, constraint in [('nome','unidades_empresa_nome_unique'), ('codigo','unidades_empresa_codigo_unique')]:
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value.execute.side_effect = Conflict(constraint)
            with patch('routes.units.psycopg2.errors.UniqueViolation',Conflict):
                response, _ = self.call(payload=self.payload, connection=connection)
            self.assertEqual(response.status_code,409)
            self.assertEqual(set(response.get_json()['campos']),{key})
            connection.rollback.assert_called_once()
            connection.commit.assert_not_called()


if __name__ == '__main__': unittest.main()
