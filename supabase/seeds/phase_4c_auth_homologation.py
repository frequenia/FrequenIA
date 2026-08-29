import os
from contextlib import closing

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash


EXPECTED_TABLES = (
    "empresas",
    "unidades",
    "equipes",
    "cargos",
    "usuarios",
    "funcionarios",
    "turnos",
    "periodos_turno",
    "funcionarios_turnos",
    "biometrias",
    "auth_sessions",
    "tentativas_faciais",
    "marcacoes",
    "ocorrencias",
    "correcoes",
    "notificacoes",
    "auditoria",
)
OLD_WORKSYNC_PROJECT_REF = "kxefcyzqjkbaakzgawnl"


def require_safe_environment():
    app_env = os.getenv("APP_ENV", "").strip().lower()
    project_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    password = os.getenv("HOMOLOGATION_TEST_PASSWORD", "")
    confirmation = os.getenv("CONFIRM_HOMOLOGATION_SEED", "")

    if app_env not in {"development", "homologation"}:
        raise RuntimeError("The authentication seed is restricted to development/homologation.")
    if not project_ref or project_ref == OLD_WORKSYNC_PROJECT_REF:
        raise RuntimeError("The target project is not an authorized FrequenIA environment.")
    if OLD_WORKSYNC_PROJECT_REF in database_url:
        raise RuntimeError("The database URL points to the old WorkSync project.")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")
    if confirmation != "FREQUENIA_HOMOLOGATION":
        raise RuntimeError("Explicit homologation seed confirmation is required.")
    if len(password) < 12:
        raise RuntimeError("HOMOLOGATION_TEST_PASSWORD must contain at least 12 characters.")

    return database_url, password


def validate_seed_state(cursor):
    cursor.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY(%s)
        ORDER BY tablename
        """,
        (list(EXPECTED_TABLES),),
    )
    existing_tables = tuple(row["tablename"] for row in cursor.fetchall())
    if existing_tables != tuple(sorted(EXPECTED_TABLES)):
        raise RuntimeError("The target does not contain the expected FrequenIA schema.")

    counts = {}
    for table_name in EXPECTED_TABLES:
        cursor.execute(f'SELECT count(*) AS total FROM public."{table_name}"')
        counts[table_name] = cursor.fetchone()["total"]

    if all(total == 0 for total in counts.values()):
        return "empty", None

    operational_tables = set(EXPECTED_TABLES) - {
        "empresas",
        "unidades",
        "equipes",
        "cargos",
        "usuarios",
        "funcionarios",
    }
    if any(counts[table_name] for table_name in operational_tables):
        raise RuntimeError("Operational data exists in the FrequenIA schema; seed cancelled.")

    cursor.execute(
        """
        SELECT u.id AS usuario_id
        FROM usuarios u
        INNER JOIN funcionarios f ON f.usuario_id = u.id
        INNER JOIN empresas e ON e.id = f.empresa_id
        INNER JOIN unidades un ON un.id = f.unidade_id
        INNER JOIN equipes eq ON eq.id = f.equipe_id
        INNER JOIN cargos c ON c.id = f.cargo_id
        WHERE u.cpf = '00000000000'
          AND u.email = 'usuario.homologacao@frequenia.invalid'
          AND f.matricula = 'HOMOLOG-0001'
          AND e.nome = 'Empresa Fictícia de Homologação'
          AND un.nome = 'Unidade Fictícia'
          AND eq.nome = 'Equipe Fictícia'
          AND c.nome = 'Cargo Fictício'
        """
    )
    fixture = cursor.fetchone()
    if not fixture:
        raise RuntimeError("The expected homologation fixture was not found; seed cancelled.")

    return "existing", fixture["usuario_id"]


def create_seed():
    database_url, password = require_safe_environment()
    password_hash = generate_password_hash(password)

    with closing(
        psycopg2.connect(database_url, sslmode="require", connect_timeout=15)
    ) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            seed_state, existing_user_id = validate_seed_state(cursor)

            if seed_state == "existing":
                cursor.execute(
                    """
                    UPDATE usuarios
                    SET senha_hash = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (password_hash, existing_user_id),
                )
                cursor.execute(
                    """
                    UPDATE funcionarios
                    SET perfil = 'administrador', updated_at = now()
                    WHERE usuario_id = %s
                    """,
                    (existing_user_id,),
                )
                conn.commit()
                print("Homologation authentication seed ready: 6 fictitious records.")
                return

            cursor.execute(
                """
                INSERT INTO empresas (nome, cnpj)
                VALUES (%s, %s)
                RETURNING id
                """,
                ("Empresa Fictícia de Homologação", "00000000000000"),
            )
            empresa_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO unidades (empresa_id, nome, codigo)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (empresa_id, "Unidade Fictícia", "HOMOLOG"),
            )
            unidade_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO equipes (empresa_id, unidade_id, nome)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (empresa_id, unidade_id, "Equipe Fictícia"),
            )
            equipe_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO cargos (empresa_id, nome)
                VALUES (%s, %s)
                RETURNING id
                """,
                (empresa_id, "Cargo Fictício"),
            )
            cargo_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO usuarios (nome, cpf, email, senha_hash)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    "Usuário Fictício de Homologação",
                    "00000000000",
                    "usuario.homologacao@frequenia.invalid",
                    password_hash,
                ),
            )
            usuario_id = cursor.fetchone()["id"]

            cursor.execute(
                """
                INSERT INTO funcionarios (
                    usuario_id,
                    empresa_id,
                    unidade_id,
                    equipe_id,
                    cargo_id,
                    matricula,
                    tipo_contrato,
                    carga_horaria_semanal,
                    perfil
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    usuario_id,
                    empresa_id,
                    unidade_id,
                    equipe_id,
                    cargo_id,
                    "HOMOLOG-0001",
                    "outro",
                    40,
                    "administrador",
                ),
            )

        conn.commit()

    print("Homologation authentication seed created: 6 fictitious records.")


if __name__ == "__main__":
    create_seed()
