import os
import re

import psycopg2


PENDING_SOURCE_USER_IDS = (34, 45, 49, 60)
OPERATIONAL_TABLES = (
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


source = psycopg2.connect(
    host=os.environ["DB_HOST"],
    port=os.environ.get("DB_PORT", "5432"),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    dbname=os.environ["DB_NAME"],
    sslmode="require",
    connect_timeout=15,
)
destination = psycopg2.connect(
    host=os.environ["NEW_DB_HOST"],
    port=os.environ.get("NEW_DB_PORT", "5432"),
    user=os.environ["NEW_DB_USER"],
    password=os.environ["NEW_DB_PASSWORD"],
    dbname=os.environ["NEW_DB_NAME"],
    sslmode="require",
    connect_timeout=15,
)

try:
    with source.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM usuarios")
        source_users = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM funcionarios")
        source_employees = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id, cpf FROM usuarios WHERE id = ANY(%s) ORDER BY id",
            (list(PENDING_SOURCE_USER_IDS),),
        )
        pending_source = cursor.fetchall()

    pending_cpfs = [re.sub(r"\D", "", row[1] or "") for row in pending_source]
    with destination.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM usuarios")
        destination_users = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM funcionarios")
        destination_employees = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM usuarios WHERE cpf = ANY(%s)", (pending_cpfs,)
        )
        pending_in_destination = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'usuarios'
              AND column_name = 'senha_hash'
            """
        )
        password_hash_nullable = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE token_hash !~ '^[0-9a-f]{64}$'),
                   count(*) FILTER (
                       WHERE used_at IS NULL
                         AND revoked_at IS NULL
                         AND expires_at > now()
                   )
            FROM password_reset_tokens
            """
        )
        reset_tokens, invalid_hashes, active_tokens = cursor.fetchone()
        operational_counts = {}
        for table in OPERATIONAL_TABLES:
            cursor.execute(f"SELECT count(*) FROM {table}")
            operational_counts[table] = cursor.fetchone()[0]

    if len(pending_source) != len(PENDING_SOURCE_USER_IDS):
        raise AssertionError("not all pending source users were found")
    if pending_in_destination != 0:
        raise AssertionError("a pending source user is already present in FrequenIA")
    if password_hash_nullable != "YES":
        raise AssertionError("usuarios.senha_hash is not nullable")
    if invalid_hashes != 0:
        raise AssertionError("a reset token is not stored as a SHA-256 hash")
    if active_tokens != 0:
        raise AssertionError("the integration test left an active reset token")
    if any(operational_counts.values()):
        raise AssertionError("operational data was changed")

    print(f"worksync_users={source_users}")
    print(f"worksync_employees={source_employees}")
    print(f"frequenia_users={destination_users}")
    print(f"frequenia_employees={destination_employees}")
    print("pending_source_users=4")
    print("pending_users_in_frequenia=0")
    print("password_hash_nullable=yes")
    print(f"password_reset_token_records={reset_tokens}")
    print("invalid_token_hashes=0")
    print("active_reset_tokens=0")
    print("operational_tables_unchanged=ok")
    print("phase4f_state_validation=success")
finally:
    source.close()
    destination.close()
