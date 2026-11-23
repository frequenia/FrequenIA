"""Executar somente no container de testes sem rede ou credenciais reais."""
from pathlib import Path
from uuid import uuid4
import os
import unittest
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from services.unit_onboarding import create_unit_with_team, validate_unit_payload

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
ACTOR = '55555555-5555-4555-8555-555555555555'
DATABASE = 'units_synthetic_' + uuid4().hex[:12]


def connect(database=DATABASE):
    return psycopg2.connect(host='127.0.0.1', dbname=database, user='postgres', connect_timeout=3)


class UnitPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('UNITS_SYNTHETIC_TEST') != '1' or not Path('/.dockerenv').exists():
            raise unittest.SkipTest('Requer container de testes isolado e UNITS_SYNTHETIC_TEST=1.')
        bootstrap = connect('postgres')
        try:
            bootstrap.autocommit = True
            with bootstrap.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DATABASE)))
        finally:
            bootstrap.close()
        with connect() as conn, conn.cursor() as cursor:
            cursor.execute("CREATE SCHEMA extensions; CREATE FUNCTION extensions.gen_random_uuid() RETURNS uuid LANGUAGE sql AS 'SELECT pg_catalog.gen_random_uuid()'; CREATE TABLE usuarios(id uuid PRIMARY KEY)")
            cursor.execute(Path('/tmp/organization.sql').read_text())
            location = Path('/tmp/location.sql').read_text().split('alter table public.marcacoes')[0]
            cursor.execute(location + '\ncommit;')
            audit = Path('/tmp/audit.sql').read_text().split('create table public.auditoria',1)[1].split('\n);',1)[0]
            cursor.execute('create table public.auditoria' + audit + '\n);')
            cursor.execute("INSERT INTO empresas(id,nome) VALUES (%s,'Empresa sintética A'),(%s,'Empresa sintética B')",(A,B))
            cursor.execute('INSERT INTO usuarios(id) VALUES (%s)',(ACTOR,))

    def setUp(self):
        self.connection = connect()
        self.addCleanup(self.connection.close)
        self.token = uuid4().hex[:12]

    def create(self, name=None, code=None, team='Geral', company=A):
        data = validate_unit_payload(dict(nome=name or self.token, codigo=code or self.token, equipe_nome=team))
        with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            result = create_unit_with_team(cursor, company_id=company, actor_id=ACTOR, data=data)
        self.connection.commit()
        return result

    def count(self, name):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM unidades WHERE nome=%s',(name,))
            return cursor.fetchone()[0]

    def test_creation_is_available_to_existing_unit_and_team_queries(self):
        result = self.create()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,nome FROM unidades WHERE empresa_id=%s AND status='ativa' AND id=%s",(A,result['unidade']['id']))
            self.assertEqual(str(cursor.fetchone()[0]),result['unidade']['id'])
            cursor.execute("SELECT nome FROM equipes WHERE empresa_id=%s AND unidade_id=%s AND status='ativa'",(A,result['unidade']['id']))
            self.assertEqual(cursor.fetchall(), [('Geral',)])
            cursor.execute('SELECT latitude,longitude,endereco_geocodificado,marcacao_mobile_ativa FROM unidades WHERE id=%s',(result['unidade']['id'],))
            self.assertEqual(cursor.fetchone(),(None,None,None,False))
            cursor.execute('SELECT count(*) FROM auditoria WHERE entidade_id IN (%s,%s)',(result['unidade']['id'],result['equipe']['id']))
            self.assertEqual(cursor.fetchone()[0],2)

    def test_code_duplicate_rolls_back_but_same_code_in_other_company_is_allowed(self):
        self.create(code=self.token)
        with self.assertRaises(psycopg2.errors.UniqueViolation) as caught:
            self.create(name='DUP-'+self.token,code=self.token)
        self.assertEqual(caught.exception.diag.constraint_name,'unidades_empresa_codigo_unique')
        self.connection.rollback()
        self.assertEqual(self.count('DUP-'+self.token),0)
        self.create(code=self.token,company=B)

    def test_name_duplicate_is_rejected(self):
        self.create(name=self.token)
        with self.assertRaises(psycopg2.errors.UniqueViolation) as caught:
            self.create(name=self.token,code='NEW-'+self.token)
        self.assertEqual(caught.exception.diag.constraint_name,'unidades_empresa_nome_unique')
        self.connection.rollback()

    def test_team_failure_removes_new_unit(self):
        with self.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE equipes ADD CONSTRAINT synthetic_team_failure CHECK (nome <> 'FORCAR_FALHA') NOT VALID")
        self.connection.commit()
        try:
            with self.assertRaises(psycopg2.errors.CheckViolation): self.create(team='FORCAR_FALHA')
            self.connection.rollback()
            self.assertEqual(self.count(self.token),0)
        finally:
            with self.connection.cursor() as cursor: cursor.execute('ALTER TABLE equipes DROP CONSTRAINT synthetic_team_failure')
            self.connection.commit()

    def test_audit_failure_removes_unit_team_and_first_audit(self):
        with self.connection.cursor() as cursor:
            cursor.execute("ALTER TABLE auditoria ADD CONSTRAINT synthetic_audit_failure CHECK (acao <> 'equipe.criada') NOT VALID")
        self.connection.commit()
        try:
            with self.assertRaises(psycopg2.errors.CheckViolation): self.create()
            self.connection.rollback()
            self.assertEqual(self.count(self.token),0)
            with self.connection.cursor() as cursor:
                cursor.execute('SELECT count(*) FROM equipes e JOIN unidades u ON u.id=e.unidade_id WHERE u.nome=%s',(self.token,))
                self.assertEqual(cursor.fetchone()[0],0)
        finally:
            with self.connection.cursor() as cursor: cursor.execute('ALTER TABLE auditoria DROP CONSTRAINT synthetic_audit_failure')
            self.connection.commit()


if __name__ == '__main__': unittest.main(verbosity=2)
