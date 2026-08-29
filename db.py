import os
from contextlib import closing

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def conectar_bd():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to connect to PostgreSQL.")

    return psycopg2.connect(database_url, sslmode="require", connect_timeout=15)


def buscar_usuario_login_por_cpf(cpf):
    with closing(conectar_bd()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, nome, senha_hash, status
                FROM usuarios
                WHERE cpf = %s
                """,
                (cpf,),
            )
            return cursor.fetchone()
def buscar_vinculos_ativos(usuario_id):
    with closing(conectar_bd()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    f.id AS funcionario_id,
                    f.empresa_id,
                    f.unidade_id,
                    f.perfil
                FROM funcionarios f
                INNER JOIN empresas e ON e.id = f.empresa_id
                WHERE f.usuario_id = %s
                  AND f.status = 'ativo'
                  AND e.status = 'ativa'
                ORDER BY f.created_at, f.id
                LIMIT 2
                """,
                (usuario_id,),
            )
            return cursor.fetchall()


def buscar_contexto_autenticado(usuario_id, funcionario_id):
    with closing(conectar_bd()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    u.id AS user_id,
                    f.id AS funcionario_id,
                    f.empresa_id
                FROM usuarios u
                INNER JOIN funcionarios f ON f.usuario_id = u.id
                INNER JOIN empresas e ON e.id = f.empresa_id
                WHERE u.id = %s
                  AND f.id = %s
                  AND u.status = 'ativo'
                  AND f.status = 'ativo'
                  AND e.status = 'ativa'
                """,
                (usuario_id, funcionario_id),
            )
            return cursor.fetchone()
