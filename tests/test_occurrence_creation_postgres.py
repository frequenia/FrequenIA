"""Reproducao opt-in, exclusivamente em PostgreSQL local sintetico e isolado."""
import os
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from flask import Flask, g
from routes.occurrences import create_occurrence


@unittest.skipUnless(os.environ.get('OCCURRENCE_DISPOSABLE_PG') == '1', 'requer banco sintetico isolado')
class OccurrenceCreationPostgresTests(unittest.TestCase):
    @staticmethod
    def connect():
        return psycopg2.connect(host='127.0.0.1', port=5432, user='postgres',
            dbname='frequenia_occurrence_synthetic',
            options='-c search_path=public,extensions', connect_timeout=5)

    def test_legacy_state_constraint_blocks_current_request(self):
        # NOT VALID preserves earlier synthetic fixtures but checks new inserts.
        with self.connect() as conn, conn.cursor() as cursor:
            cursor.execute("""ALTER TABLE correcoes ADD CONSTRAINT synthetic_legacy_state
                CHECK (estado IN ('solicitada','em_analise_gestor','encaminhada_rh',
                    'em_analise_rh','aprovada','rejeitada','cancelada')) NOT VALID""")
        try:
            self._create_lunch_correction(expected_status=500)
        finally:
            with self.connect() as conn, conn.cursor() as cursor:
                cursor.execute('ALTER TABLE correcoes DROP CONSTRAINT synthetic_legacy_state')
        self._create_lunch_correction(expected_status=201)

    def test_lunch_type_correction_with_all_migrations(self):
        self._create_lunch_correction(expected_status=201)

    def _create_lunch_correction(self, expected_status):
        errors = []

        class Connection(psycopg2.extensions.connection):
            def rollback(self):
                error = sys.exc_info()[1]
                if error:
                    errors.append(str(error))  # Somente fixtures sinteticas deste teste.
                return super().rollback()

        def connect():
            return psycopg2.connect(host='127.0.0.1', port=5432, user='postgres',
                dbname='frequenia_occurrence_synthetic', connection_factory=Connection,
                options='-c search_path=public,extensions', connect_timeout=5)

        company, unit, user, employee, marking = [str(uuid4()) for _ in range(5)]
        with connect() as conn, conn.cursor() as cursor:
            cursor.execute("INSERT INTO empresas(id,nome) VALUES(%s,'Empresa sintetica')", (company,))
            cursor.execute("INSERT INTO unidades(id,empresa_id,nome) VALUES(%s,%s,'Unidade sintetica')", (unit, company))
            fixture_cpf = str(int(uuid4().hex, 16))[-11:]
            cursor.execute("INSERT INTO usuarios(id,nome,cpf,senha_hash) VALUES(%s,'Teste sintetico',%s,'fixture')", (user,fixture_cpf))
            cursor.execute("INSERT INTO funcionarios(id,usuario_id,empresa_id,unidade_id,matricula) VALUES(%s,%s,%s,%s,'SYNTHETIC')", (employee,user,company,unit))
            cursor.execute("INSERT INTO marcacoes(id,empresa_id,funcionario_id,instante,tipo,origem) VALUES(%s,%s,%s,clock_timestamp(),'saida','manual')", (marking,company,employee))
        app = Flask(__name__)
        with app.test_request_context('/api/ocorrencias', method='POST', json={
            'tipo':'tipo_incorreto', 'marcacao_id':marking,
            'tipo_marcacao_solicitado':'saida_intervalo', 'motivo':'Correcao sintetica de almoco',
        }):
            g.auth_context = {'empresa_id':company,'funcionario_id':employee,'user_id':user,'perfil':'funcionario'}
            with patch('routes.occurrences.conectar_bd', side_effect=connect):
                response, status = create_occurrence.__wrapped__()
            self.assertEqual(status, expected_status, str(errors))
            if expected_status == 201:
                self.assertEqual(response.get_json()['status'], 'pendente_gestor')
            else:
                self.assertTrue(any('synthetic_legacy_state' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
