import os
import secrets
from datetime import date
from uuid import uuid4

import psycopg2
import psycopg2.extras
import requests
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash


BASE_URL = os.getenv("PHASE7_BASE_URL", "http://127.0.0.1:5000")
ADMIN_CPF = "00000000000"
ADMIN_PASSWORD = os.environ["PHASE7_ADMIN_PASSWORD"]
DATABASE_URL = os.environ["DATABASE_URL"]
PROFILE_LABELS = {
    "administrador": "Administrador",
    "funcionario": "Funcionário",
    "gestor": "Gestor",
    "rh": "RH",
}


def expect(response, status, name):
    if response.status_code != status:
        raise AssertionError(f"{name}: expected {status}, got {response.status_code}")
    print(f"{name}={status}")


def cpf_from_seed(seed):
    digits = [int(value) for value in f"{seed:09d}"[-9:]]
    first_sum = sum(digits[index] * (10 - index) for index in range(9))
    first_remainder = first_sum % 11
    digits.append(0 if first_remainder < 2 else 11 - first_remainder)
    second_sum = sum(digits[index] * (11 - index) for index in range(10))
    second_remainder = second_sum % 11
    digits.append(0 if second_remainder < 2 else 11 - second_remainder)
    return "".join(str(value) for value in digits)


def login(client, cpf, password):
    response = client.post(
        f"{BASE_URL}/login",
        json={"cpf": cpf, "senha": password},
        timeout=30,
    )
    expect(response, 200, "login")
    payload = response.json()
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise AssertionError("login did not return tokens")
    return payload


def input_value(html, element_id):
    field = BeautifulSoup(html, "html.parser").find(id=element_id)
    if field is None:
        raise AssertionError(f"profile field not found: {element_id}")
    return field.get("value", "")


def validate_profile(response, expected):
    expect(response, 200, f"profile_{expected['perfil']}")
    values = {
        "nome": input_value(response.text, "nome"),
        "cpf": input_value(response.text, "cpf"),
        "email": input_value(response.text, "email"),
        "matricula": input_value(response.text, "matricula"),
        "perfil": input_value(response.text, "perfil"),
        "empresa": input_value(response.text, "empresa"),
        "unidade": input_value(response.text, "unidade"),
        "equipe": input_value(response.text, "equipe"),
        "cargo": input_value(response.text, "cargo"),
    }
    wanted = {
        "nome": expected["nome"],
        "cpf": expected["cpf"],
        "email": expected["email"] or "Não informado",
        "matricula": expected["matricula"],
        "perfil": PROFILE_LABELS[expected["perfil"]],
        "empresa": expected["empresa_nome"],
        "unidade": expected["unidade_nome"],
        "equipe": expected["equipe_nome"],
        "cargo": expected["cargo_nome"],
    }
    if values != wanted:
        raise AssertionError("profile values do not match authenticated employee")

    forbidden_markers = (
        "senha_hash",
        "refresh_token",
        "access_token",
        "token_hash",
        "embedding",
        "database_url",
        "postgresql://",
    )
    lowered = response.text.lower()
    if any(marker in lowered for marker in forbidden_markers):
        raise AssertionError("profile response exposes a forbidden field")


connection = psycopg2.connect(
    DATABASE_URL,
    sslmode="require",
    connect_timeout=15,
)
connection.autocommit = True
cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
fixture_user_ids = []
fixture_employee_ids = []
fixtures = []


try:
    cursor.execute(
        """
        SELECT
            u.id AS usuario_id,
            u.nome,
            u.cpf,
            u.email,
            f.id AS funcionario_id,
            f.empresa_id,
            f.unidade_id,
            f.equipe_id,
            f.cargo_id,
            f.matricula,
            f.perfil,
            e.nome AS empresa_nome,
            un.nome AS unidade_nome,
            eq.nome AS equipe_nome,
            c.nome AS cargo_nome
        FROM usuarios u
        JOIN funcionarios f ON f.usuario_id = u.id
        JOIN empresas e ON e.id = f.empresa_id
        JOIN unidades un ON un.id = f.unidade_id AND un.empresa_id = f.empresa_id
        JOIN equipes eq
          ON eq.id = f.equipe_id
         AND eq.empresa_id = f.empresa_id
         AND eq.unidade_id = f.unidade_id
        JOIN cargos c ON c.id = f.cargo_id AND c.empresa_id = f.empresa_id
        WHERE u.cpf = %s AND f.perfil = 'administrador'
        LIMIT 1
        """,
        (ADMIN_CPF,),
    )
    administrator = cursor.fetchone()
    if not administrator:
        raise AssertionError("administrator profile fixture not found")

    cursor.execute(
        """
        SELECT count(*)
        FROM usuarios u
        JOIN funcionarios f ON f.usuario_id = u.id
        WHERE u.status = 'bloqueado'
          AND u.senha_hash IS NULL
          AND f.status = 'afastado'
        """
    )
    pending_first_access_before = cursor.fetchone()["count"]

    suffix = secrets.token_hex(6)
    for index, profile in enumerate(("funcionario", "gestor", "rh"), start=1):
        user_id = str(uuid4())
        employee_id = str(uuid4())
        password = secrets.token_urlsafe(18)
        cpf = cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000)
        name = f"Fixture Perfil {profile.upper()}"
        email = f"phase7.{profile}.{suffix}@frequenia.invalid"
        registration = f"P7-{index}-{suffix}"

        cursor.execute(
            """
            INSERT INTO usuarios (id, nome, cpf, email, senha_hash, status)
            VALUES (%s,%s,%s,%s,%s,'ativo')
            """,
            (user_id, name, cpf, email, generate_password_hash(password)),
        )
        cursor.execute(
            """
            INSERT INTO funcionarios (
                id, usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                matricula, data_admissao, tipo_contrato,
                carga_horaria_semanal, perfil, status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'efetivo',40,%s,'ativo')
            """,
            (
                employee_id,
                user_id,
                administrator["empresa_id"],
                administrator["unidade_id"],
                administrator["equipe_id"],
                administrator["cargo_id"],
                registration,
                date.today(),
                profile,
            ),
        )
        fixture_user_ids.append(user_id)
        fixture_employee_ids.append(employee_id)
        fixtures.append(
            {
                "usuario_id": user_id,
                "funcionario_id": employee_id,
                "nome": name,
                "cpf": cpf,
                "email": email,
                "matricula": registration,
                "perfil": profile,
                "password": password,
                "empresa_nome": administrator["empresa_nome"],
                "unidade_nome": administrator["unidade_nome"],
                "equipe_nome": administrator["equipe_nome"],
                "cargo_nome": administrator["cargo_nome"],
            }
        )

    anonymous = requests.Session()
    expect(anonymous.get(f"{BASE_URL}/perfil", timeout=30), 401, "anonymous_profile")

    admin_client = requests.Session()
    admin_tokens = login(admin_client, ADMIN_CPF, ADMIN_PASSWORD)
    validate_profile(admin_client.get(f"{BASE_URL}/perfil", timeout=30), administrator)
    expect(
        admin_client.get(f"{BASE_URL}/listarUsuarios", timeout=30),
        200,
        "admin_rbac_regression",
    )
    expect(
        requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            timeout=30,
        ),
        200,
        "auth_me_regression",
    )

    isolated = admin_client.get(
        f"{BASE_URL}/perfil",
        params={
            "usuario_id": fixtures[0]["usuario_id"],
            "funcionario_id": fixtures[0]["funcionario_id"],
            "empresa_id": str(uuid4()),
        },
        timeout=30,
    )
    validate_profile(isolated, administrator)
    if fixtures[0]["nome"] in isolated.text:
        raise AssertionError("arbitrary IDs changed the authenticated profile")
    print("profile_id_isolation=ok")

    refreshed = admin_client.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": admin_tokens["refresh_token"]},
        timeout=30,
    )
    expect(refreshed, 200, "refresh_regression")
    validate_profile(admin_client.get(f"{BASE_URL}/perfil", timeout=30), administrator)
    expect(
        admin_client.post(
            f"{BASE_URL}/auth/logout",
            headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
            timeout=30,
        ),
        200,
        "logout_regression",
    )
    expect(admin_client.get(f"{BASE_URL}/perfil", timeout=30), 401, "revoked_profile")

    for fixture in fixtures:
        client = requests.Session()
        tokens = login(client, fixture["cpf"], fixture["password"])
        validate_profile(client.get(f"{BASE_URL}/perfil", timeout=30), fixture)
        if fixture["perfil"] in {"gestor", "rh"}:
            expect(
                client.get(f"{BASE_URL}/listarUsuarios", timeout=30),
                403,
                f"{fixture['perfil']}_admin_denied",
            )
        expect(
            client.post(
                f"{BASE_URL}/auth/logout",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=30,
            ),
            200,
            f"{fixture['perfil']}_logout",
        )

    expect(requests.get(f"{BASE_URL}/health", timeout=30), 200, "health_regression")
    expect(requests.get(f"{BASE_URL}/status", timeout=30), 200, "status_regression")
    expect(
        requests.get(f"{BASE_URL}/cadastroUsuario", timeout=30),
        401,
        "admin_page_auth_regression",
    )
    recovery = requests.post(
        f"{BASE_URL}/auth/password/forgot",
        json={"identifier": "phase7.missing@frequenia.invalid"},
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
        WHERE u.status = 'bloqueado'
          AND u.senha_hash IS NULL
          AND f.status = 'afastado'
        """
    )
    if cursor.fetchone()["count"] != pending_first_access_before:
        raise AssertionError("pending first-access users changed")
    print("first_access_state_unchanged=ok")
    print("phase7_profile_integration=success")
finally:
    try:
        if fixture_user_ids:
            cursor.execute(
                "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
                (fixture_user_ids,),
            )
        if fixture_employee_ids:
            cursor.execute(
                "DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])",
                (fixture_employee_ids,),
            )
        if fixture_user_ids:
            cursor.execute(
                "DELETE FROM usuarios WHERE id = ANY(%s::uuid[])",
                (fixture_user_ids,),
            )
    finally:
        cursor.close()
        connection.close()
