import hashlib
import os
import secrets
from uuid import uuid4

import jwt
import psycopg2
import psycopg2.extras
import requests
from werkzeug.security import check_password_hash


BASE_URL = os.getenv("PHASE4G_BASE_URL", "http://127.0.0.1:5000")
COMPANY_ID = "2fc04ab1-cb6a-4fcc-90b5-7d80216b9ab0"
PASSWORD = "F4G!" + secrets.token_hex(16)
RAW_TOKEN = secrets.token_urlsafe(32)
TOKEN_HASH = hashlib.sha256(RAW_TOKEN.encode("utf-8")).hexdigest()
USER_ID = None
EMPLOYEE_ID = None


def expect(response, status, name):
    if response.status_code != status:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                payload.pop("test_token", None)
        except ValueError:
            payload = "non-json response"
        raise AssertionError(
            f"{name}: expected {status}, received {response.status_code}; response={payload}"
        )
    print(f"{name}={status}")


connection = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require", connect_timeout=15)
try:
    with connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT un.id AS unidade_id, eq.id AS equipe_id, c.id AS cargo_id
                FROM unidades un
                JOIN equipes eq
                  ON eq.empresa_id = un.empresa_id AND eq.unidade_id = un.id
                JOIN cargos c ON c.empresa_id = un.empresa_id
                WHERE un.empresa_id = %s
                  AND un.nome = 'Prefeitura - Unidade Piloto'
                  AND un.status = 'ativa'
                  AND eq.status = 'ativa'
                  AND c.status = 'ativo'
                ORDER BY eq.nome, c.nome
                LIMIT 1
                """,
                (COMPANY_ID,),
            )
            organization = cursor.fetchone()
            if not organization:
                raise AssertionError("homologation organization fixture is missing")

            suffix = str(uuid4().int)[-10:]
            cpf = "8" + suffix
            email = f"phase4g.control.{uuid4().hex}@frequenia.invalid"
            employee_number = f"F4G-{uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO usuarios (nome, cpf, email, senha_hash, status)
                VALUES ('Fixture Primeiro Acesso 4G', %s, %s, NULL, 'bloqueado')
                RETURNING id
                """,
                (cpf, email),
            )
            USER_ID = str(cursor.fetchone()["id"])
            cursor.execute(
                """
                INSERT INTO funcionarios (
                    usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                    matricula, tipo_contrato, perfil, status
                )
                VALUES (%s,%s,%s,%s,%s,%s,'efetivo','funcionario','afastado')
                RETURNING id
                """,
                (
                    USER_ID,
                    COMPANY_ID,
                    organization["unidade_id"],
                    organization["equipe_id"],
                    organization["cargo_id"],
                    employee_number,
                ),
            )
            EMPLOYEE_ID = str(cursor.fetchone()["id"])
            cursor.execute(
                """
                INSERT INTO password_reset_tokens (
                    usuario_id, token_hash, purpose, expires_at
                )
                VALUES (%s, %s, 'first_access', now() + interval '30 minutes')
                """,
                (USER_ID, TOKEN_HASH),
            )

    session = requests.Session()
    expect(
        session.post(
            f"{BASE_URL}/login", json={"cpf": cpf, "senha": PASSWORD}, timeout=30
        ),
        401,
        "pre_first_access_login_http",
    )
    expect(
        session.post(
            f"{BASE_URL}/auth/password/reset",
            json={"token": RAW_TOKEN, "new_password": "curta"},
            timeout=30,
        ),
        400,
        "short_password_http",
    )
    expect(
        session.post(
            f"{BASE_URL}/auth/password/reset",
            json={"token": RAW_TOKEN, "new_password": PASSWORD},
            timeout=30,
        ),
        200,
        "first_access_reset_http",
    )

    with connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT u.senha_hash, u.status AS user_status,
                       f.status AS employee_status, t.used_at,
                       (SELECT count(*) FROM password_reset_tokens active
                        WHERE active.usuario_id = u.id
                          AND active.purpose = 'first_access'
                          AND active.used_at IS NULL
                          AND active.revoked_at IS NULL
                          AND active.expires_at > now()) AS active_tokens
                FROM usuarios u
                JOIN funcionarios f ON f.usuario_id = u.id
                JOIN password_reset_tokens t
                  ON t.usuario_id = u.id AND t.token_hash = %s
                WHERE u.id = %s
                """,
                (TOKEN_HASH, USER_ID),
            )
            state = cursor.fetchone()
            if (
                not state
                or state["user_status"] != "ativo"
                or state["employee_status"] != "ativo"
                or state["used_at"] is None
                or state["active_tokens"] != 0
                or not check_password_hash(state["senha_hash"], PASSWORD)
            ):
                raise AssertionError("first-access state transition failed")
    print("first_access_state_transition=ok")

    login = session.post(
        f"{BASE_URL}/login", json={"cpf": cpf, "senha": PASSWORD}, timeout=30
    )
    expect(login, 200, "post_first_access_login_http")
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    if "cpf" in claims or claims.get("funcionario_id") != EMPLOYEE_ID:
        raise AssertionError("JWT claims regression")
    expect(
        requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            timeout=30,
        ),
        200,
        "post_first_access_auth_me_http",
    )
    expect(
        session.post(
            f"{BASE_URL}/auth/password/reset",
            json={"token": RAW_TOKEN, "new_password": PASSWORD},
            timeout=30,
        ),
        400,
        "used_first_access_token_http",
    )
    print("phase4g_first_access_integration=success")
finally:
    connection.rollback()
    if USER_ID:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM password_reset_tokens WHERE usuario_id = %s", (USER_ID,))
                cursor.execute("DELETE FROM funcionarios WHERE usuario_id = %s", (USER_ID,))
                cursor.execute("DELETE FROM usuarios WHERE id = %s", (USER_ID,))
        print("isolated_fixture_cleanup=ok")
    connection.close()
