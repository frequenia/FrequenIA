import hashlib
import os
import re
import secrets

import jwt
import psycopg2
import requests
from werkzeug.security import check_password_hash


BASE_URL = "http://127.0.0.1:5000"
IDENTIFIER = "usuario.homologacao@frequenia.invalid"
CPF = "00000000000"
ORIGINAL_PASSWORD = os.environ["PHASE4F_EXISTING_PASSWORD"]
NEW_PASSWORD = os.environ["PHASE4F_NEW_PASSWORD"]
TEST_KEY = os.environ["PASSWORD_RESET_TEST_KEY"]


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


def forgot(session, identifier, controlled=False):
    headers = {"X-Password-Reset-Test-Key": TEST_KEY} if controlled else {}
    return session.post(
        f"{BASE_URL}/auth/password/forgot",
        json={"identifier": identifier},
        headers=headers,
        timeout=30,
    )


def reset(session, token, password):
    return session.post(
        f"{BASE_URL}/auth/password/reset",
        json={"token": token, "new_password": password},
        timeout=30,
    )


def controlled_token(session):
    response = forgot(session, IDENTIFIER, controlled=True)
    expect(response, 200, "controlled_request_http")
    token = response.json().get("test_token")
    if not token or len(token) < 32:
        raise AssertionError("controlled test token was not returned")
    return token


session = requests.Session()
expect(session.get(f"{BASE_URL}/health", timeout=30), 200, "health_http")
expect(session.get(f"{BASE_URL}/status", timeout=30), 200, "status_http")

initial_login = session.post(
    f"{BASE_URL}/login", json={"cpf": CPF, "senha": ORIGINAL_PASSWORD}, timeout=30
)
expect(initial_login, 200, "existing_login_http")
access_token = initial_login.json()["access_token"]
claims = jwt.decode(access_token, options={"verify_signature": False})
if "cpf" in claims or not claims.get("funcionario_id"):
    raise AssertionError("JWT claims regression")
expect(
    requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    ),
    200,
    "auth_me_http",
)
expect(session.get(f"{BASE_URL}/cadastroUsuario", timeout=30), 200, "admin_registration_page_http")
expect(session.get(f"{BASE_URL}/listarUsuarios", timeout=30), 200, "admin_listing_http")

eligible_public = forgot(session, IDENTIFIER)
missing_public = forgot(session, "conta-inexistente@frequenia.invalid")
expect(eligible_public, 200, "eligible_public_request_http")
expect(missing_public, 200, "missing_public_request_http")
if eligible_public.json() != missing_public.json():
    raise AssertionError("public response permits account enumeration")
if "test_token" in eligible_public.json() or "test_token" in missing_public.json():
    raise AssertionError("public response exposed a test token")
print("public_response_generic=ok")

token_a = controlled_token(session)
expect(reset(session, token_a, "curta"), 400, "short_password_http")

connection = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require", connect_timeout=15)
with connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT token_hash, used_at FROM password_reset_tokens WHERE token_hash = %s",
            (hashlib.sha256(token_a.encode()).hexdigest(),),
        )
        row = cursor.fetchone()
        if not row or row[0] == token_a or row[1] is not None:
            raise AssertionError("token hash persistence or short-password atomicity failed")
print("token_hash_only_and_short_password_atomicity=ok")

token_b = controlled_token(session)
expect(reset(session, token_a, NEW_PASSWORD), 400, "revoked_token_http")
with connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE password_reset_tokens
               SET created_at = now() - interval '2 minutes',
                   expires_at = now() - interval '1 minute'
             WHERE token_hash = %s
            """,
            (hashlib.sha256(token_b.encode()).hexdigest(),),
        )
expect(reset(session, token_b, NEW_PASSWORD), 400, "expired_token_http")

invalid_token = secrets.token_urlsafe(32)
expect(reset(session, invalid_token, NEW_PASSWORD), 400, "invalid_token_http")

token_c = controlled_token(session)
expect(
    session.post(
        f"{BASE_URL}/auth/password/validate", json={"token": token_c}, timeout=30
    ),
    200,
    "valid_token_validation_http",
)
expect(reset(session, token_c, NEW_PASSWORD), 200, "valid_token_http")
expect(reset(session, token_c, NEW_PASSWORD), 400, "used_token_http")

new_login = requests.post(
    f"{BASE_URL}/login", json={"cpf": CPF, "senha": NEW_PASSWORD}, timeout=30
)
expect(new_login, 200, "new_password_login_http")
expect(
    requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
        timeout=30,
    ),
    200,
    "new_password_auth_me_http",
)

token_d = controlled_token(session)
expect(reset(session, token_d, ORIGINAL_PASSWORD), 200, "restore_password_http")
restored_login = requests.post(
    f"{BASE_URL}/login", json={"cpf": CPF, "senha": ORIGINAL_PASSWORD}, timeout=30
)
expect(restored_login, 200, "restored_login_http")

raw_tokens = (token_a, token_b, token_c, token_d, invalid_token)
with connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT u.senha_hash
            FROM usuarios u
            WHERE u.email = %s
            """,
            (IDENTIFIER,),
        )
        password_hash = cursor.fetchone()[0]
        if password_hash in {ORIGINAL_PASSWORD, NEW_PASSWORD} or not check_password_hash(
            password_hash, ORIGINAL_PASSWORD
        ):
            raise AssertionError("final password hash validation failed")
        cursor.execute(
            """
            SELECT count(*)
            FROM password_reset_tokens
            WHERE token_hash !~ '^[0-9a-f]{64}$'
            """
        )
        if cursor.fetchone()[0] != 0:
            raise AssertionError("invalid stored token hash format")
        cursor.execute("SELECT token_hash FROM password_reset_tokens")
        stored_hashes = [row[0] for row in cursor.fetchall()]
        if any(raw in stored for raw in raw_tokens for stored in stored_hashes):
            raise AssertionError("raw token found in database")
connection.close()
print("password_hash_and_raw_token_storage=ok")
print("phase4f_integration=success")
