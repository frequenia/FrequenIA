"""Cookie dedicado de terminal; somente identificadores sintéticos."""
import time
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g, jsonify, session
from utils.terminal_auth import (TERMINAL_COOKIE, TERMINAL_COOKIE_MAX_AGE,
                                 remember_terminal, terminal_required)

TERMINAL='11111111-1111-4111-8111-111111111111'
COMPANY='22222222-2222-4222-8222-222222222222'


class TerminalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__); self.app.secret_key='synthetic-signing-key'
        @self.app.get('/activate-synthetic')
        def activate(): return remember_terminal(jsonify(ok=True),TERMINAL)
        @self.app.get('/logout-synthetic')
        def logout(): session.clear(); return jsonify(ok=True)
        @self.app.get('/probe')
        @terminal_required
        def probe(): return jsonify(g.terminal_context)
        self.client=self.app.test_client()

    def probe(self,client=None,active=True):
        connection=MagicMock()
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value=(TERMINAL,COMPANY) if active else None
        with patch('utils.terminal_auth.conectar_bd',return_value=connection):
            response=(client or self.client).get('/probe')
        return response,cursor

    def test_persistent_private_cookie_survives_reopening_and_logout(self):
        response=self.client.get('/activate-synthetic')
        header=response.headers['Set-Cookie']
        for part in ['HttpOnly','SameSite=Strict','Max-Age=31536000','Expires=']:
            self.assertIn(part,header)
        reopened=self.app.test_client()
        reopened.set_cookie(TERMINAL_COOKIE,self.client.get_cookie(TERMINAL_COOKIE).value)
        reopened.get('/logout-synthetic')
        response,cursor=self.probe(reopened)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['terminal_id'],TERMINAL)
        self.assertEqual(cursor.execute.call_args.args[1],(TERMINAL,))
        self.assertIn("status = 'ativo'",cursor.execute.call_args.args[0])

    def test_revocation_is_checked_even_with_persistent_cookie(self):
        self.client.get('/activate-synthetic')
        response,_=self.probe(active=False)
        self.assertEqual(response.status_code,401)
        self.assertNotIn('Set-Cookie',response.headers)

    def test_tampered_cookie_cannot_authenticate(self):
        self.client.get('/activate-synthetic')
        original=self.client.get_cookie(TERMINAL_COOKIE).value
        self.client.set_cookie(TERMINAL_COOKIE,original+'tampered')
        response,cursor=self.probe()
        self.assertEqual(response.status_code,401); cursor.execute.assert_not_called()

    def test_old_cookie_is_accepted_and_renewed_after_database_validation(self):
        self.client.get('/activate-synthetic')
        original=self.client.get_cookie(TERMINAL_COOKIE).value
        future=time.time()+TERMINAL_COOKIE_MAX_AGE+2
        with patch('itsdangerous.timed.time.time',return_value=future):
            response,cursor=self.probe()
        self.assertEqual(response.status_code,200)
        cursor.execute.assert_called_once()
        renewed=self.client.get_cookie(TERMINAL_COOKIE).value
        self.assertNotEqual(original,renewed)
        self.assertIn('Max-Age=31536000',response.headers['Set-Cookie'])

    def test_legacy_activation_upgrades_only_after_database_validation(self):
        with self.client.session_transaction() as state: state['terminal_ponto_id']=TERMINAL
        response,_=self.probe()
        self.assertEqual(response.status_code,200)
        self.assertIsNotNone(self.client.get_cookie(TERMINAL_COOKIE))
        self.client.delete_cookie(TERMINAL_COOKIE)
        response,_=self.probe(active=False)
        self.assertEqual(response.status_code,401)
        self.assertIsNone(self.client.get_cookie(TERMINAL_COOKIE))

    def test_production_cookie_secure(self):
        self.app.config['SESSION_COOKIE_SECURE']=True
        self.assertIn('Secure',self.client.get('/activate-synthetic').headers['Set-Cookie'])


if __name__=='__main__': unittest.main()
