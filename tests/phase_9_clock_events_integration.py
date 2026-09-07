import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import psycopg2
import psycopg2.extras
import requests
from werkzeug.security import generate_password_hash


BASE_URL = os.getenv("PHASE9_BASE_URL", "http://127.0.0.1:5000")
DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = f"Phase9!{secrets.token_urlsafe(14)}"


def expect(response, status, name):
    if response.status_code != status:
        raise AssertionError(
            f"{name}: expected {status}, got {response.status_code}: "
            f"{response.text[:300]}"
        )
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


def login(cpf):
    response = requests.post(
        f"{BASE_URL}/login",
        json={"cpf": cpf, "senha": PASSWORD},
        timeout=30,
    )
    expect(response, 200, f"login_{cpf[-4:]}")
    return response.json()


def headers(token, idempotency_key=None):
    result = {"Authorization": f"Bearer {token}"}
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


connection = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=15)
connection.autocommit = True
cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

company_ids = [str(uuid4()), str(uuid4())]
unit_ids = [str(uuid4()), str(uuid4())]
team_ids = [str(uuid4()), str(uuid4())]
role_ids = [str(uuid4()), str(uuid4())]
user_ids = [str(uuid4()) for _ in range(4)]
employee_ids = [str(uuid4()) for _ in range(4)]
cpfs = [cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000) for _ in range(4)]
clock_event_ids = []


try:
    for index in range(2):
        cursor.execute(
            "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
            (company_ids[index], f"Fase 9 Empresa {uuid4()}"),
        )
        cursor.execute(
            "INSERT INTO unidades (id, empresa_id, nome) VALUES (%s, %s, %s)",
            (unit_ids[index], company_ids[index], f"Unidade {uuid4()}"),
        )
        cursor.execute(
            """
            INSERT INTO equipes (id, empresa_id, unidade_id, nome)
            VALUES (%s, %s, %s, %s)
            """,
            (team_ids[index], company_ids[index], unit_ids[index], f"Equipe {uuid4()}"),
        )
        cursor.execute(
            "INSERT INTO cargos (id, empresa_id, nome) VALUES (%s, %s, %s)",
            (role_ids[index], company_ids[index], f"Cargo {uuid4()}"),
        )

    profiles = ["administrador", "funcionario", "funcionario", "funcionario"]
    companies = [0, 0, 0, 1]
    for index, profile in enumerate(profiles):
        company_index = companies[index]
        cursor.execute(
            """
            INSERT INTO usuarios (id, nome, cpf, senha_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_ids[index],
                f"Fase 9 Usuário {index}",
                cpfs[index],
                generate_password_hash(PASSWORD),
            ),
        )
        cursor.execute(
            """
            INSERT INTO funcionarios (
                id, usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                matricula, perfil, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ativo')
            """,
            (
                employee_ids[index],
                user_ids[index],
                company_ids[company_index],
                unit_ids[company_index],
                team_ids[company_index],
                role_ids[company_index],
                f"F9-{uuid4()}",
                profile,
            ),
        )

    expect(requests.get(f"{BASE_URL}/health", timeout=10), 200, "health")
    expect(requests.get(f"{BASE_URL}/status", timeout=10), 200, "status")
    expect(
        requests.get(f"{BASE_URL}/api/marcacoes", timeout=10),
        401,
        "unauthenticated_list_rejected",
    )
    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "entrada"},
            timeout=10,
        ),
        401,
        "unauthenticated_clock_rejected",
    )

    admin = login(cpfs[0])
    employee = login(cpfs[1])
    employee_without_schedule = login(cpfs[2])
    foreign_employee = login(cpfs[3])
    admin_headers = headers(admin["access_token"])
    employee_headers = headers(employee["access_token"])
    empty_headers = headers(employee_without_schedule["access_token"])
    foreign_headers = headers(foreign_employee["access_token"])

    expect(
        requests.get(f"{BASE_URL}/auth/me", headers=admin_headers, timeout=20),
        200,
        "auth_me",
    )
    expect(
        requests.get(f"{BASE_URL}/perfil", headers=admin_headers, timeout=20),
        200,
        "perfil",
    )
    expect(
        requests.get(f"{BASE_URL}/api/jornada", headers=employee_headers, timeout=20),
        200,
        "own_schedule_regression",
    )
    expect(
        requests.get(f"{BASE_URL}/jornadas", headers=admin_headers, timeout=20),
        200,
        "admin_schedules_ui_regression",
    )

    idempotency_key = str(uuid4())
    response = requests.post(
        f"{BASE_URL}/api/marcacoes",
        json={"tipo": "entrada"},
        headers=headers(employee["access_token"], idempotency_key),
        timeout=20,
    )
    expect(response, 201, "own_clock_event")
    created = response.json()["marcacao"]
    clock_event_ids.append(created["id"])
    if created["tipo"] != "entrada" or created["origem"] != "manual":
        raise AssertionError("clock event did not preserve server-controlled values")
    if created["estado"] != "confirmada":
        raise AssertionError("manual clock event was not confirmed")
    if datetime.fromisoformat(created["instante"]).tzinfo is None:
        raise AssertionError("clock event timestamp is not timezone-aware")

    cursor.execute(
        """
        SELECT empresa_id, funcionario_id, tentativa_facial_id
        FROM marcacoes WHERE id = %s
        """,
        (created["id"],),
    )
    stored = cursor.fetchone()
    if (
        str(stored["empresa_id"]) != company_ids[0]
        or str(stored["funcionario_id"]) != employee_ids[1]
        or stored["tentativa_facial_id"] is not None
    ):
        raise AssertionError("clock event identity did not come from authentication")

    repeated = requests.post(
        f"{BASE_URL}/api/marcacoes",
        json={"tipo": "entrada"},
        headers=headers(employee["access_token"], idempotency_key),
        timeout=20,
    )
    expect(repeated, 200, "idempotent_retry")
    if (
        repeated.json()["marcacao"]["id"] != created["id"]
        or repeated.json().get("reutilizada") is not True
    ):
        raise AssertionError("idempotent retry did not return the original event")

    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "saida_intervalo"},
            headers=headers(employee["access_token"], str(uuid4())),
            timeout=20,
        ),
        409,
        "recent_duplicate_rejected",
    )
    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "saida", "funcionario_id": employee_ids[2]},
            headers=employee_headers,
            timeout=20,
        ),
        400,
        "arbitrary_employee_rejected",
    )
    expect(
        requests.get(
            f"{BASE_URL}/api/marcacoes",
            params={"empresa_id": company_ids[1]},
            headers=employee_headers,
            timeout=20,
        ),
        400,
        "arbitrary_company_rejected",
    )
    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "saida", "instante": "2000-01-01T00:00:00Z"},
            headers=employee_headers,
            timeout=20,
        ),
        400,
        "client_timestamp_rejected",
    )
    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "tipo_inventado"},
            headers=empty_headers,
            timeout=20,
        ),
        400,
        "invalid_type_rejected",
    )

    cursor.execute(
        "SELECT count(*) AS total FROM funcionarios_turnos WHERE funcionario_id = %s",
        (employee_ids[2],),
    )
    if cursor.fetchone()["total"] != 0:
        raise AssertionError("no-schedule fixture unexpectedly has a shift")

    def concurrent_clock(key):
        return requests.post(
            f"{BASE_URL}/api/marcacoes",
            json={"tipo": "entrada"},
            headers=headers(employee_without_schedule["access_token"], key),
            timeout=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent = list(
            executor.map(concurrent_clock, [str(uuid4()), str(uuid4())])
        )
    statuses = sorted(response.status_code for response in concurrent)
    if statuses != [201, 409]:
        raise AssertionError(f"concurrent requests returned {statuses}")
    successful = next(response for response in concurrent if response.status_code == 201)
    clock_event_ids.append(successful.json()["marcacao"]["id"])
    print("concurrent_duplicate_protection=201,409")

    cursor.execute(
        "SELECT count(*) AS total FROM marcacoes WHERE funcionario_id = %s",
        (employee_ids[2],),
    )
    if cursor.fetchone()["total"] != 1:
        raise AssertionError("concurrent requests created duplicate clock events")
    print("employee_without_schedule_clocked=201")

    historical_ids = [str(uuid4()), str(uuid4())]
    clock_event_ids.extend(historical_ids)
    cursor.execute(
        """
        INSERT INTO marcacoes (
            id, empresa_id, funcionario_id, instante, tipo, origem, estado
        ) VALUES
            (%s, %s, %s, clock_timestamp() - interval '10 minutes',
             'entrada', 'manual', 'confirmada'),
            (%s, %s, %s, clock_timestamp() - interval '5 minutes',
             'saida', 'manual', 'confirmada')
        """,
        (
            historical_ids[0],
            company_ids[0],
            employee_ids[1],
            historical_ids[1],
            company_ids[0],
            employee_ids[1],
        ),
    )
    foreign_clock_id = str(uuid4())
    clock_event_ids.append(foreign_clock_id)
    cursor.execute(
        """
        INSERT INTO marcacoes (
            id, empresa_id, funcionario_id, instante, tipo, origem, estado
        ) VALUES (%s, %s, %s, clock_timestamp(), 'entrada', 'manual', 'confirmada')
        """,
        (foreign_clock_id, company_ids[1], employee_ids[3]),
    )

    own_list = requests.get(
        f"{BASE_URL}/api/marcacoes", headers=employee_headers, timeout=20
    )
    expect(own_list, 200, "own_clock_events_list")
    own_rows = own_list.json()["marcacoes"]
    if [row["id"] for row in own_rows] != [created["id"], historical_ids[1], historical_ids[0]]:
        raise AssertionError("own clock events are not deterministically ordered")
    if foreign_clock_id in {row["id"] for row in own_rows}:
        raise AssertionError("own listing leaked another company")

    admin_list = requests.get(
        f"{BASE_URL}/api/admin/funcionarios/{employee_ids[1]}/marcacoes",
        headers=admin_headers,
        timeout=20,
    )
    expect(admin_list, 200, "admin_company_employee_list")
    if [row["id"] for row in admin_list.json()["marcacoes"]] != [
        created["id"],
        historical_ids[1],
        historical_ids[0],
    ]:
        raise AssertionError("administrative clock event listing is incorrect")
    expect(
        requests.get(
            f"{BASE_URL}/api/admin/funcionarios/{employee_ids[1]}/marcacoes",
            headers=employee_headers,
            timeout=20,
        ),
        403,
        "employee_admin_list_rejected",
    )
    expect(
        requests.get(
            f"{BASE_URL}/api/admin/funcionarios/{employee_ids[3]}/marcacoes",
            headers=admin_headers,
            timeout=20,
        ),
        404,
        "foreign_employee_admin_list_rejected",
    )

    expect(
        requests.put(
            f"{BASE_URL}/api/marcacoes",
            json={"id": created["id"], "tipo": "saida"},
            headers=employee_headers,
            timeout=20,
        ),
        405,
        "clock_event_update_unavailable",
    )
    expect(
        requests.delete(
            f"{BASE_URL}/api/marcacoes",
            json={"id": created["id"]},
            headers=employee_headers,
            timeout=20,
        ),
        405,
        "clock_event_delete_unavailable",
    )

    cursor.execute(
        "UPDATE funcionarios SET status = 'afastado' WHERE id = %s",
        (employee_ids[2],),
    )
    expect(
        requests.get(f"{BASE_URL}/api/marcacoes", headers=empty_headers, timeout=20),
        401,
        "inactive_employee_rejected",
    )
    cursor.execute(
        "UPDATE funcionarios SET status = 'ativo' WHERE id = %s",
        (employee_ids[2],),
    )

    cursor.execute(
        "UPDATE empresas SET status = 'inativa' WHERE id = %s",
        (company_ids[1],),
    )
    expect(
        requests.get(f"{BASE_URL}/api/marcacoes", headers=foreign_headers, timeout=20),
        401,
        "inactive_company_rejected",
    )
    cursor.execute(
        "UPDATE empresas SET status = 'ativa' WHERE id = %s",
        (company_ids[1],),
    )

    logout = requests.post(
        f"{BASE_URL}/auth/logout", headers=foreign_headers, timeout=20
    )
    expect(logout, 200, "logout")
    expect(
        requests.get(f"{BASE_URL}/api/marcacoes", headers=foreign_headers, timeout=20),
        401,
        "revoked_session_rejected",
    )

    print("phase_9_clock_events=ok")
finally:
    cursor.execute(
        "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
        (user_ids,),
    )
    cursor.execute(
        "DELETE FROM marcacoes WHERE id = ANY(%s::uuid[])",
        (clock_event_ids,),
    )
    cursor.execute(
        "DELETE FROM funcionarios_turnos WHERE funcionario_id = ANY(%s::uuid[])",
        (employee_ids,),
    )
    cursor.execute(
        "DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])",
        (employee_ids,),
    )
    cursor.execute("DELETE FROM usuarios WHERE id = ANY(%s::uuid[])", (user_ids,))
    cursor.execute("DELETE FROM equipes WHERE id = ANY(%s::uuid[])", (team_ids,))
    cursor.execute("DELETE FROM cargos WHERE id = ANY(%s::uuid[])", (role_ids,))
    cursor.execute("DELETE FROM unidades WHERE id = ANY(%s::uuid[])", (unit_ids,))
    cursor.execute("DELETE FROM empresas WHERE id = ANY(%s::uuid[])", (company_ids,))
    cursor.close()
    connection.close()
