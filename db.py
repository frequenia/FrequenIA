import os
from contextlib import closing
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
_RUNTIME_SUPABASE_CA = "/etc/ssl/certs/supabase-prod-ca-2021.crt"


def _database_ssl_options():
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    production = app_env == "production"
    sslmode = os.getenv(
        "DATABASE_SSLMODE", "verify-full" if production else "require"
    ).strip().lower()
    if sslmode not in _SSL_MODES:
        raise RuntimeError("DATABASE_SSLMODE has an unsupported value.")

    options = {"sslmode": sslmode}
    if sslmode in {"verify-ca", "verify-full"}:
        default_root = _RUNTIME_SUPABASE_CA if production else ""
        sslrootcert = os.getenv("DATABASE_SSLROOTCERT", default_root).strip()
        if not sslrootcert:
            raise RuntimeError(
                "DATABASE_SSLROOTCERT is required when the database SSL mode verifies the server."
            )
        if not Path(sslrootcert).is_file():
            raise RuntimeError("DATABASE_SSLROOTCERT does not identify a readable certificate file.")
        options["sslrootcert"] = sslrootcert
    return options


def conectar_bd():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to connect to PostgreSQL.")

    # pgvector e pgcrypto sao instalados no schema ``extensions`` pelas migrations.
    # O search_path explicito evita depender de configuracao externa da role.
    return psycopg2.connect(
        database_url,
        connect_timeout=15,
        options="-c search_path=public,extensions",
        **_database_ssl_options(),
    )


def buscar_usuario_login_por_cpf(cpf):
    with closing(conectar_bd()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, nome, senha_hash, status, perfil_sistema,
                       primeiro_acesso_pendente
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
                    f.empresa_id,
                    f.perfil
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


def buscar_sessao_access(session_id, usuario_id, funcionario_id=None):
    with closing(conectar_bd()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    s.id AS session_id,
                    s.familia_id,
                    u.id AS user_id,
                    f.id AS funcionario_id,
                    f.empresa_id,
                    COALESCE(u.perfil_sistema, f.perfil) AS perfil
                FROM auth_sessions s
                INNER JOIN usuarios u ON u.id = s.usuario_id
                LEFT JOIN funcionarios f
                    ON f.id = s.funcionario_id
                   AND f.empresa_id = s.empresa_id
                   AND f.usuario_id = u.id
                LEFT JOIN empresas e ON e.id = f.empresa_id
                WHERE s.id = %s
                  AND s.usuario_id = %s
                  AND s.funcionario_id IS NOT DISTINCT FROM %s
                  AND s.revoked_at IS NULL
                  AND s.rotated_at IS NULL
                  AND s.expires_at > now()
                  AND u.status = 'ativo'
                  AND (
                    (u.perfil_sistema = 'administrador_geral'
                     AND s.empresa_id IS NULL AND s.funcionario_id IS NULL)
                    OR
                    (u.perfil_sistema IS NULL
                     AND f.status = 'ativo' AND e.status = 'ativa')
                  )
                """,
                (session_id, usuario_id, funcionario_id),
            )
            return cursor.fetchone()
