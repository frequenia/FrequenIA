import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import psycopg2
import requests


BASE_URL = os.getenv("PHASE5_BASE_URL", "http://127.0.0.1:5000")
CPF = "00000000000"
PASSWORD = os.environ["PHASE5_EXISTING_PASSWORD"]
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = "HS256"
PENDING_USER_IDS = [
    "084bdc2f-835e-4c60-92e3-5a5ee628face",
    "7e5e8dbd-f562-41b5-8c9e-a27bb1c4c86c",
    "9787bb11-878a-42a0-a74e-7982a7abac31",
    "8853e2af-01be-4832-92c5-f34969792507",
]


def expect(response, status, name):
    if response.status_code != status:
        raise AssertionError(f"{name}: expected {status}, got {response.status_code}")


def login(client):
    response = client.post(
        f"{BASE_URL}/login",
        json={"cpf": CPF, "senha": PASSWORD},
        timeout=30,
    )
    expect(response, 200, "login")
    payload = response.json()
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise AssertionError("login did not return both tokens")
    cookie = response.headers.get("Set-Cookie", "")
    if "HttpOnly" not in cookie or "SameSite=Lax" not in cookie:
        raise AssertionError("refresh cookie flags are incomplete")
    return payload


def auth_me(access_token):
    return requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )


def refresh(refresh_token):
    return requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=30,
    )


def logout(access_token):
    return requests.post(
        f"{BASE_URL}/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )


connection = psycopg2.connect(
    DATABASE_URL,
    sslmode="require",
    connect_timeout=15,
)
connection.autocommit = True
cursor = connection.cursor()
families = set()


def inspect_access(access_token):
    claims = jwt.decode(
        access_token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "funcionario_id", "sid", "type", "iat", "exp"]},
    )
    allowed = {"sub", "funcionario_id", "sid", "type", "iat", "exp"}
    if set(claims) - allowed or claims.get("type") != "access":
        raise AssertionError("access token claims are not minimal")
    cursor.execute(
        """
        SELECT familia_id, refresh_token_hash
        FROM auth_sessions
        WHERE id = %s
        """,
        (claims["sid"],),
    )
    row = cursor.fetchone()
    if not row:
        raise AssertionError("access sid has no auth_session")
    families.add(str(row[0]))
    return claims, row[1]


try:
    client_a = requests.Session()
    login_a = login(client_a)
    claims_a, stored_hash_a = inspect_access(login_a["access_token"])
    expected_hash_a = hashlib.sha256(login_a["refresh_token"].encode()).hexdigest()
    if stored_hash_a != expected_hash_a or stored_hash_a == login_a["refresh_token"]:
        raise AssertionError("refresh token was not stored exclusively as SHA-256")
    expect(auth_me(login_a["access_token"]), 200, "valid_access")
    expect(auth_me(secrets.token_urlsafe(32)), 401, "invalid_access")

    expired_payload = {
        "sub": claims_a["sub"],
        "funcionario_id": claims_a["funcionario_id"],
        "sid": claims_a["sid"],
        "type": "access",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    expired_access = jwt.encode(
        expired_payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    expect(auth_me(expired_access), 401, "expired_access")

    rotated_b = refresh(login_a["refresh_token"])
    expect(rotated_b, 200, "refresh_a_to_b")
    tokens_b = rotated_b.json()
    expect(auth_me(tokens_b["access_token"]), 200, "access_b")
    inspect_access(tokens_b["access_token"])

    rotated_c = refresh(tokens_b["refresh_token"])
    expect(rotated_c, 200, "refresh_b_to_c")
    tokens_c = rotated_c.json()
    expect(auth_me(tokens_c["access_token"]), 200, "access_c")
    inspect_access(tokens_c["access_token"])

    expect(refresh(login_a["refresh_token"]), 401, "reuse_refresh_a")
    expect(auth_me(tokens_c["access_token"]), 401, "family_revoked_after_reuse")
    expect(refresh(tokens_c["refresh_token"]), 401, "current_refresh_after_reuse")

    logout_login = login(requests.Session())
    inspect_access(logout_login["access_token"])
    expect(logout(logout_login["access_token"]), 200, "logout")
    expect(auth_me(logout_login["access_token"]), 401, "access_after_logout")
    expect(refresh(logout_login["refresh_token"]), 401, "refresh_after_logout")

    simultaneous_a = login(requests.Session())
    simultaneous_b = login(requests.Session())
    inspect_access(simultaneous_a["access_token"])
    inspect_access(simultaneous_b["access_token"])
    expect(logout(simultaneous_a["access_token"]), 200, "logout_session_a")
    expect(auth_me(simultaneous_b["access_token"]), 200, "session_b_after_logout_a")
    simultaneous_b_rotated = refresh(simultaneous_b["refresh_token"])
    expect(simultaneous_b_rotated, 200, "refresh_session_b")
    tokens_simultaneous_b = simultaneous_b_rotated.json()
    inspect_access(tokens_simultaneous_b["access_token"])
    expect(logout(tokens_simultaneous_b["access_token"]), 200, "logout_session_b")

    recovery = requests.post(
        f"{BASE_URL}/auth/password/forgot",
        json={"identifier": "conta-inexistente@frequenia.invalid"},
        timeout=30,
    )
    expect(recovery, 200, "password_recovery_regression")
    if "test_token" in recovery.json():
        raise AssertionError("public recovery exposed a test token")

    cursor.execute(
        """
        SELECT count(*)
        FROM usuarios u
        JOIN funcionarios f ON f.usuario_id = u.id
        WHERE u.id = ANY(%s::uuid[])
          AND u.status = 'bloqueado'
          AND u.senha_hash IS NULL
          AND f.status = 'afastado'
        """,
        (PENDING_USER_IDS,),
    )
    if cursor.fetchone()[0] != 4:
        raise AssertionError("pending first-access users changed")

    cursor.execute(
        """
        SELECT count(*),
               count(*) FILTER (
                   WHERE revoked_at IS NULL
                     AND rotated_at IS NULL
                     AND expires_at > now()
               ),
               count(*) FILTER (WHERE revoked_at IS NOT NULL),
               count(*) FILTER (WHERE expires_at <= now())
        FROM auth_sessions
        WHERE familia_id = ANY(%s::uuid[])
        """,
        (list(families),),
    )
    created, active, revoked, expired = cursor.fetchone()
    print("login_http=200")
    print("access_valid_http=200")
    print("access_invalid_http=401")
    print("access_expired_http=401")
    print("refresh_rotation=ok")
    print("refresh_reuse_family_revocation=ok")
    print("logout_revocation=ok")
    print("simultaneous_sessions=ok")
    print("password_recovery_regression=ok")
    print("first_access_pending_users_unchanged=4")
    print(f"test_sessions_created={created}")
    print(f"test_sessions_active={active}")
    print(f"test_sessions_revoked={revoked}")
    print(f"test_sessions_expired={expired}")
    print("phase5_integration=success")
finally:
    cursor.close()
    connection.close()
