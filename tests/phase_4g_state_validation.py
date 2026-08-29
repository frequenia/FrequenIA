import os
import re

import psycopg2
import requests


BASE_URL = os.getenv("PHASE4G_BASE_URL", "http://127.0.0.1:5000")
PENDING_SOURCE_USER_IDS = (34, 45, 49, 60)
OPERATIONAL_TABLES = (
    "biometrias",
    "auth_sessions",
    "turnos",
    "periodos_turno",
    "funcionarios_turnos",
    "tentativas_faciais",
    "marcacoes",
    "ocorrencias",
    "correcoes",
    "notificacoes",
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
    source.set_session(readonly=True, autocommit=False)
    with source.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM usuarios")
        source_users = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM funcionarios")
        source_employees = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id, cpf FROM usuarios WHERE id = ANY(%s) ORDER BY id",
            (list(PENDING_SOURCE_USER_IDS),),
        )
        source_rows = cursor.fetchall()
    source.rollback()
    if len(source_rows) != 4:
        raise AssertionError("authorized WorkSync users diverged")

    cpfs = [re.sub(r"\D", "", row[1] or "") for row in source_rows]
    with destination.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM usuarios")
        destination_users = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM funcionarios")
        destination_employees = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT count(*),
                   count(*) FILTER (
                       WHERE u.status = 'bloqueado'
                         AND u.senha_hash IS NULL
                         AND f.status = 'afastado'
                   ),
                   count(*) FILTER (
                       WHERE t.purpose = 'first_access'
                         AND t.used_at IS NULL
                         AND t.revoked_at IS NULL
                         AND t.expires_at > now()
                   ),
                   count(*) FILTER (WHERE t.token_hash !~ '^[0-9a-f]{64}$')
            FROM usuarios u
            JOIN funcionarios f ON f.usuario_id = u.id
            LEFT JOIN password_reset_tokens t ON t.usuario_id = u.id
            WHERE u.cpf = ANY(%s)
            """,
            (cpfs,),
        )
        migrated_rows, pending_states, active_tokens, invalid_hashes = cursor.fetchone()
        operational_counts = {}
        for table in OPERATIONAL_TABLES:
            cursor.execute(f"SELECT count(*) FROM {table}")
            operational_counts[table] = cursor.fetchone()[0]
    destination.rollback()

    if source_users != 8 or source_employees != 8:
        raise AssertionError("WorkSync counts changed")
    if destination_users != 10 or destination_employees != 10:
        raise AssertionError("FrequenIA user/employee counts diverged")
    if migrated_rows != 4 or pending_states != 4:
        raise AssertionError("pending first-access state diverged")
    if active_tokens != 4 or invalid_hashes != 0:
        raise AssertionError("first-access token state diverged")
    if any(operational_counts.values()):
        raise AssertionError("an out-of-scope operational table changed")

    for cpf in cpfs:
        response = requests.post(
            f"{BASE_URL}/login",
            json={"cpf": cpf, "senha": "Fase4G!LoginDeveFalhar"},
            timeout=30,
        )
        if response.status_code != 401:
            raise AssertionError("a pending first-access user authenticated")

    existing_login = requests.post(
        f"{BASE_URL}/login",
        json={"cpf": "00000000000", "senha": os.environ["PHASE4G_EXISTING_PASSWORD"]},
        timeout=30,
    )
    if existing_login.status_code != 200:
        raise AssertionError("existing homologation login regressed")
    auth_me = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {existing_login.json()['access_token']}"},
        timeout=30,
    )
    if auth_me.status_code != 200:
        raise AssertionError("existing homologation /auth/me regressed")

    print("worksync_users=8")
    print("worksync_employees=8")
    print("frequenia_users=10")
    print("frequenia_employees=10")
    print("phase4g_pending_users=4")
    print("phase4g_active_first_access_tokens=4")
    print("pre_first_access_login_http=401_for_all")
    print("existing_login_http=200")
    print("existing_auth_me_http=200")
    print("operational_tables_unchanged=ok")
    print("phase4g_state_validation=success")
finally:
    source.close()
    destination.close()
