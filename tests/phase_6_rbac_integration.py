import os
import secrets
from datetime import date
from uuid import uuid4

import jwt
import psycopg2
import psycopg2.extras
import requests
from werkzeug.security import generate_password_hash


BASE_URL = os.getenv("PHASE6_BASE_URL", "http://127.0.0.1:5000")
ADMIN_CPF = "00000000000"
ADMIN_PASSWORD = os.environ["PHASE6_ADMIN_PASSWORD"]
DATABASE_URL = os.environ["DATABASE_URL"]


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
        raise AssertionError("login did not return both tokens")
    return payload


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


connection = psycopg2.connect(
    DATABASE_URL,
    sslmode="require",
    connect_timeout=15,
)
connection.autocommit = True
cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

employee_user_id = str(uuid4())
employee_id = str(uuid4())
foreign_company_id = str(uuid4())
foreign_unit_id = str(uuid4())
foreign_team_id = str(uuid4())
foreign_role_id = str(uuid4())
foreign_user_id = str(uuid4())
foreign_employee_id = str(uuid4())
created_api_employee_id = None
created_api_user_id = None

employee_password = secrets.token_urlsafe(18)
api_user_password = secrets.token_urlsafe(18)
employee_cpf = cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000)
foreign_cpf = cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000)
api_user_cpf = cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000)
suffix = secrets.token_hex(6)


try:
    cursor.execute(
        """
        SELECT f.empresa_id, un.id AS unidade_id, eq.id AS equipe_id, c.id AS cargo_id
        FROM funcionarios f
        JOIN usuarios u ON u.id = f.usuario_id
        JOIN unidades un ON un.empresa_id = f.empresa_id AND un.status = 'ativa'
        JOIN equipes eq
          ON eq.empresa_id = un.empresa_id
         AND eq.unidade_id = un.id
         AND eq.status = 'ativa'
        JOIN cargos c ON c.empresa_id = f.empresa_id AND c.status = 'ativo'
        WHERE u.cpf = %s AND f.perfil = 'administrador'
        LIMIT 1
        """,
        (ADMIN_CPF,),
    )
    organization = cursor.fetchone()
    if not organization:
        raise AssertionError("active administrator organization fixture not found")

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

    cursor.execute(
        """
        INSERT INTO usuarios (id, nome, cpf, email, senha_hash, status)
        VALUES (%s, %s, %s, %s, %s, 'ativo')
        """,
        (
            employee_user_id,
            "Fixture Funcionário RBAC",
            employee_cpf,
            f"phase6.employee.{suffix}@frequenia.invalid",
            generate_password_hash(employee_password),
        ),
    )
    cursor.execute(
        """
        INSERT INTO funcionarios (
            id, usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
            matricula, data_admissao, tipo_contrato,
            carga_horaria_semanal, perfil, status
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'efetivo',40,'funcionario','ativo')
        """,
        (
            employee_id,
            employee_user_id,
            organization["empresa_id"],
            organization["unidade_id"],
            organization["equipe_id"],
            organization["cargo_id"],
            f"P6-F-{suffix}",
            date.today(),
        ),
    )

    cursor.execute(
        "INSERT INTO empresas (id, nome, cnpj, status) VALUES (%s,%s,%s,'ativa')",
        (
            foreign_company_id,
            f"Fixture Empresa Externa {suffix}",
            f"9{secrets.randbelow(10**13):013d}",
        ),
    )
    cursor.execute(
        "INSERT INTO unidades (id, empresa_id, nome, codigo) VALUES (%s,%s,%s,%s)",
        (foreign_unit_id, foreign_company_id, "Unidade Externa", f"UE-{suffix}"),
    )
    cursor.execute(
        "INSERT INTO equipes (id, empresa_id, unidade_id, nome) VALUES (%s,%s,%s,%s)",
        (foreign_team_id, foreign_company_id, foreign_unit_id, "Equipe Externa"),
    )
    cursor.execute(
        "INSERT INTO cargos (id, empresa_id, nome) VALUES (%s,%s,%s)",
        (foreign_role_id, foreign_company_id, "Cargo Externo"),
    )
    cursor.execute(
        """
        INSERT INTO usuarios (id, nome, cpf, email, senha_hash, status)
        VALUES (%s,%s,%s,%s,%s,'ativo')
        """,
        (
            foreign_user_id,
            "Fixture Externa RBAC",
            foreign_cpf,
            f"phase6.foreign.{suffix}@frequenia.invalid",
            generate_password_hash(secrets.token_urlsafe(18)),
        ),
    )
    cursor.execute(
        """
        INSERT INTO funcionarios (
            id, usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
            matricula, tipo_contrato, perfil, status
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,'efetivo','funcionario','ativo')
        """,
        (
            foreign_employee_id,
            foreign_user_id,
            foreign_company_id,
            foreign_unit_id,
            foreign_team_id,
            foreign_role_id,
            f"P6-X-{suffix}",
        ),
    )

    anonymous = requests.Session()
    expect(anonymous.get(f"{BASE_URL}/listarUsuarios", timeout=30), 401, "anonymous_admin_api")
    expect(anonymous.get(f"{BASE_URL}/cadastroUsuario", timeout=30), 401, "anonymous_admin_page")

    employee_client = requests.Session()
    employee_tokens = login(employee_client, employee_cpf, employee_password)
    employee_access = employee_tokens["access_token"]
    claims = jwt.decode(employee_access, options={"verify_signature": False})
    if "cpf" in claims or "perfil" in claims or "empresa_id" in claims:
        raise AssertionError("JWT contains authorization or personal data")

    expect(employee_client.get(f"{BASE_URL}/cadastroUsuario", timeout=30), 403, "employee_admin_page")
    expect(
        requests.get(
            f"{BASE_URL}/listarUsuarios",
            headers=bearer(employee_access),
            timeout=30,
        ),
        403,
        "employee_admin_api",
    )
    elevation_payload = {
        "nome": "Tentativa Elevação",
        "email": f"phase6.elevation.{suffix}@frequenia.invalid",
        "telefone": "",
        "cpf": api_user_cpf,
        "matricula": f"P6-E-{suffix}",
        "perfil": "administrador",
        "tipo_contrato": "efetivo",
        "data_admissao": str(date.today()),
        "carga_horaria_semanal": 40,
        "empresa_id": str(organization["empresa_id"]),
        "unidade_id": str(organization["unidade_id"]),
        "equipe_id": str(organization["equipe_id"]),
        "cargo_id": str(organization["cargo_id"]),
        "senha": api_user_password,
    }
    expect(
        requests.post(
            f"{BASE_URL}/cadastrar_usuario",
            json=elevation_payload,
            headers=bearer(employee_access),
            timeout=30,
        ),
        403,
        "employee_privilege_escalation",
    )
    expect(
        requests.post(
            f"{BASE_URL}/atualizar_usuario",
            json={**elevation_payload, "funcionario_id": employee_id},
            headers=bearer(employee_access),
            timeout=30,
        ),
        403,
        "employee_edit_attempt",
    )
    expect(
        requests.post(
            f"{BASE_URL}/atualizar_status_usuario",
            json={"funcionario_id": employee_id},
            headers=bearer(employee_access),
            timeout=30,
        ),
        403,
        "employee_status_attempt",
    )

    refreshed = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": employee_tokens["refresh_token"]},
        timeout=30,
    )
    expect(refreshed, 200, "refresh_regression")
    employee_access = refreshed.json()["access_token"]
    expect(
        requests.post(
            f"{BASE_URL}/auth/logout",
            headers=bearer(employee_access),
            timeout=30,
        ),
        200,
        "logout_regression",
    )
    expect(
        requests.get(
            f"{BASE_URL}/listarUsuarios",
            headers=bearer(employee_access),
            timeout=30,
        ),
        401,
        "revoked_session_admin_api",
    )

    admin_client = requests.Session()
    admin_tokens = login(admin_client, ADMIN_CPF, ADMIN_PASSWORD)
    admin_access = admin_tokens["access_token"]
    expect(admin_client.get(f"{BASE_URL}/cadastroUsuario", timeout=30), 200, "admin_page")
    users_response = admin_client.get(f"{BASE_URL}/listarUsuarios", timeout=30)
    expect(users_response, 200, "admin_list_users")
    returned_employee_ids = {str(item["funcionario_id"]) for item in users_response.json()}
    if foreign_employee_id in returned_employee_ids:
        raise AssertionError("cross-company employee leaked in user listing")

    companies_response = admin_client.get(f"{BASE_URL}/listarEmpresas", timeout=30)
    expect(companies_response, 200, "admin_list_companies")
    returned_company_ids = {str(item["id"]) for item in companies_response.json()}
    if returned_company_ids != {str(organization["empresa_id"])}:
        raise AssertionError("company listing escaped authenticated tenant")

    expect(
        admin_client.get(
            f"{BASE_URL}/listar_unidades",
            params={"empresa_id": foreign_company_id},
            timeout=30,
        ),
        403,
        "arbitrary_company_id",
    )
    expect(
        admin_client.get(
            f"{BASE_URL}/editarUsuario",
            params={"funcionario_id": foreign_employee_id},
            timeout=30,
        ),
        404,
        "cross_company_employee_read",
    )

    create_payload = {
        **elevation_payload,
        "nome": "Fixture API RBAC",
        "email": f"phase6.api.{suffix}@frequenia.invalid",
        "cpf": api_user_cpf,
        "matricula": f"P6-A-{suffix}",
        "perfil": "funcionario",
    }
    created = admin_client.post(
        f"{BASE_URL}/cadastrar_usuario",
        json=create_payload,
        timeout=30,
    )
    expect(created, 201, "admin_create_user")
    cursor.execute(
        """
        SELECT f.id AS funcionario_id, f.usuario_id
        FROM funcionarios f
        JOIN usuarios u ON u.id = f.usuario_id
        WHERE u.cpf = %s AND f.empresa_id = %s
        """,
        (api_user_cpf, organization["empresa_id"]),
    )
    api_fixture = cursor.fetchone()
    if not api_fixture:
        raise AssertionError("admin-created user not found in authorized company")
    created_api_employee_id = str(api_fixture["funcionario_id"])
    created_api_user_id = str(api_fixture["usuario_id"])

    expect(
        admin_client.get(
            f"{BASE_URL}/editarUsuario",
            params={"funcionario_id": created_api_employee_id},
            timeout=30,
        ),
        200,
        "admin_edit_page",
    )
    update_payload = {
        **create_payload,
        "funcionario_id": created_api_employee_id,
        "nome": "Fixture API RBAC Editada",
    }
    update_payload.pop("senha", None)
    expect(
        admin_client.post(
            f"{BASE_URL}/atualizar_usuario",
            json=update_payload,
            timeout=30,
        ),
        200,
        "admin_update_user",
    )
    expect(
        admin_client.post(
            f"{BASE_URL}/atualizar_usuario",
            json={
                **update_payload,
                "empresa_id": foreign_company_id,
                "unidade_id": foreign_unit_id,
                "equipe_id": foreign_team_id,
                "cargo_id": foreign_role_id,
            },
            timeout=30,
        ),
        403,
        "admin_cross_company_update",
    )
    expect(
        admin_client.post(
            f"{BASE_URL}/atualizar_usuario",
            json={**update_payload, "unidade_id": foreign_unit_id},
            timeout=30,
        ),
        400,
        "admin_cross_company_link_uuid",
    )
    expect(
        admin_client.post(
            f"{BASE_URL}/atualizar_status_usuario",
            json={"funcionario_id": created_api_employee_id},
            timeout=30,
        ),
        200,
        "admin_change_status",
    )
    expect(
        admin_client.post(
            f"{BASE_URL}/atualizar_status_usuario",
            json={"funcionario_id": created_api_employee_id},
            timeout=30,
        ),
        200,
        "admin_restore_status",
    )
    expect(
        admin_client.post(
            f"{BASE_URL}/deletar_usuario",
            json={"funcionario_id": created_api_employee_id},
            timeout=30,
        ),
        200,
        "admin_deactivate_user",
    )

    expect(requests.get(f"{BASE_URL}/health", timeout=30), 200, "health_regression")
    expect(requests.get(f"{BASE_URL}/status", timeout=30), 200, "status_regression")
    expect(
        requests.get(
            f"{BASE_URL}/auth/me",
            headers=bearer(admin_access),
            timeout=30,
        ),
        200,
        "auth_me_regression",
    )
    recovery = requests.post(
        f"{BASE_URL}/auth/password/forgot",
        json={"identifier": "phase6.missing@frequenia.invalid"},
        timeout=30,
    )
    expect(recovery, 200, "password_recovery_regression")
    if "test_token" in recovery.json():
        raise AssertionError("public recovery exposed test token")

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

    expect(
        requests.post(
            f"{BASE_URL}/auth/logout",
            headers=bearer(admin_access),
            timeout=30,
        ),
        200,
        "admin_logout",
    )
    print("phase6_rbac_integration=success")
finally:
    test_user_ids = [employee_user_id, foreign_user_id]
    test_employee_ids = [employee_id, foreign_employee_id]
    if created_api_user_id:
        test_user_ids.append(created_api_user_id)
    if created_api_employee_id:
        test_employee_ids.append(created_api_employee_id)

    try:
        cursor.execute(
            "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
            (test_user_ids,),
        )
        cursor.execute(
            "DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])",
            (test_employee_ids,),
        )
        cursor.execute(
            "DELETE FROM usuarios WHERE id = ANY(%s::uuid[])",
            (test_user_ids,),
        )
        cursor.execute("DELETE FROM cargos WHERE id = %s", (foreign_role_id,))
        cursor.execute("DELETE FROM equipes WHERE id = %s", (foreign_team_id,))
        cursor.execute("DELETE FROM unidades WHERE id = %s", (foreign_unit_id,))
        cursor.execute("DELETE FROM empresas WHERE id = %s", (foreign_company_id,))
    finally:
        cursor.close()
        connection.close()
