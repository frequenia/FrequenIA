import os
import secrets
from datetime import date
from uuid import uuid4

import psycopg2
import psycopg2.extras
import requests
from werkzeug.security import generate_password_hash


BASE_URL = os.getenv("PHASE8_BASE_URL", "http://127.0.0.1:5000")
DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = f"Phase8!{secrets.token_urlsafe(14)}"
PASSWORD_RESET_TEST_KEY = os.environ["PASSWORD_RESET_TEST_KEY"]


def expect(response, status, name):
    if response.status_code != status:
        raise AssertionError(
            f"{name}: expected {status}, got {response.status_code}: {response.text[:300]}"
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


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def login(cpf):
    response = requests.post(
        f"{BASE_URL}/login",
        json={"cpf": cpf, "senha": PASSWORD},
        timeout=30,
    )
    expect(response, 200, f"login_{cpf[-4:]}")
    payload = response.json()
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise AssertionError("login did not return both tokens")
    return payload


connection = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=15)
connection.autocommit = True
cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

company_ids = [str(uuid4()), str(uuid4())]
unit_ids = [str(uuid4()), str(uuid4())]
team_ids = [str(uuid4()), str(uuid4())]
role_ids = [str(uuid4()), str(uuid4())]
user_ids = [str(uuid4()) for _ in range(4)]
employee_ids = [str(uuid4()) for _ in range(4)]
foreign_turn_id = str(uuid4())
created_turn_ids = []
cpfs = [cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000) for _ in range(4)]


try:
    for index in range(2):
        cursor.execute(
            "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
            (company_ids[index], f"Fase 8 Empresa {uuid4()}"),
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
                f"Fase 8 Usuário {index}",
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
                f"F8-{uuid4()}",
                profile,
            ),
        )

    cursor.execute(
        """
        INSERT INTO turnos (id, empresa_id, nome)
        VALUES (%s, %s, %s)
        """,
        (foreign_turn_id, company_ids[1], f"Turno estrangeiro {uuid4()}"),
    )
    cursor.execute(
        """
        INSERT INTO periodos_turno (
            empresa_id, turno_id, dia_semana, ordem, inicio, fim
        ) VALUES (%s, %s, 1, 1, '08:00', '12:00')
        """,
        (company_ids[1], foreign_turn_id),
    )

    expect(requests.get(f"{BASE_URL}/health", timeout=10), 200, "health")
    expect(requests.get(f"{BASE_URL}/status", timeout=10), 200, "status")

    admin = login(cpfs[0])
    employee = login(cpfs[1])
    employee_without_schedule = login(cpfs[2])
    admin_headers = auth_headers(admin["access_token"])
    employee_headers = auth_headers(employee["access_token"])
    empty_headers = auth_headers(employee_without_schedule["access_token"])

    expect(
        requests.get(f"{BASE_URL}/auth/me", headers=admin_headers, timeout=20),
        200,
        "auth_me",
    )
    refresh = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": admin["refresh_token"]},
        timeout=20,
    )
    expect(refresh, 200, "refresh")
    admin = refresh.json()
    admin_headers = auth_headers(admin["access_token"])
    expect(
        requests.get(f"{BASE_URL}/perfil", headers=admin_headers, timeout=20),
        200,
        "perfil",
    )
    expect(
        requests.get(
            f"{BASE_URL}/cadastroUsuario", headers=admin_headers, timeout=20
        ),
        200,
        "user_registration_page",
    )
    expect(
        requests.get(f"{BASE_URL}/listarUsuarios", headers=admin_headers, timeout=20),
        200,
        "user_listing",
    )
    expect(
        requests.get(f"{BASE_URL}/recuperacaoSenha", timeout=20),
        200,
        "password_recovery_page",
    )
    expect(
        requests.get(f"{BASE_URL}/redefinicaoSenha", timeout=20),
        200,
        "first_access_password_page",
    )
    expect(
        requests.get(f"{BASE_URL}/api/admin/turnos", timeout=20),
        401,
        "admin_unauthenticated",
    )
    expect(
        requests.get(
            f"{BASE_URL}/api/admin/turnos", headers=employee_headers, timeout=20
        ),
        403,
        "admin_employee_forbidden",
    )

    simple_payload = {
        "nome": f"Administrativo {uuid4()}",
        "timezone": "America/Sao_Paulo",
        "periodos": [
            {"dia_semana": 1, "ordem": 1, "inicio": "08:00", "fim": "12:00"},
            {"dia_semana": 1, "ordem": 2, "inicio": "13:00", "fim": "17:00"},
        ],
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/turnos",
        json=simple_payload,
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 201, "simple_shift")
    simple_turn = response.json()["turno"]
    created_turn_ids.append(simple_turn["id"])
    if [period["ordem"] for period in simple_turn["periodos"]] != [1, 2]:
        raise AssertionError("simple shift periods are not ordered")

    multiple_payload = {
        "nome": f"Múltiplos períodos {uuid4()}",
        "periodos": [
            {"dia_semana": 1, "ordem": 1, "inicio": "08:00", "fim": "10:00"},
            {"dia_semana": 1, "ordem": 2, "inicio": "10:15", "fim": "12:00"},
            {"dia_semana": 1, "ordem": 3, "inicio": "13:00", "fim": "15:00"},
            {"dia_semana": 1, "ordem": 4, "inicio": "15:15", "fim": "17:00"},
        ],
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/turnos",
        json=multiple_payload,
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 201, "multiple_periods")
    multiple_turn = response.json()["turno"]
    created_turn_ids.append(multiple_turn["id"])
    if len(multiple_turn["periodos"]) != 4:
        raise AssertionError("multiple shift did not preserve all periods")

    overlap_payload = {
        "nome": f"Sobreposição {uuid4()}",
        "periodos": [
            {"dia_semana": 1, "ordem": 1, "inicio": "08:00", "fim": "12:00"},
            {"dia_semana": 1, "ordem": 2, "inicio": "11:00", "fim": "15:00"},
        ],
    }
    expect(
        requests.post(
            f"{BASE_URL}/api/admin/turnos",
            json=overlap_payload,
            headers=admin_headers,
            timeout=20,
        ),
        400,
        "overlap_rejected",
    )

    night_payload = {
        "nome": f"Noturno {uuid4()}",
        "periodos": [
            {
                "dia_semana": 1,
                "ordem": 1,
                "inicio": "22:00",
                "fim": "02:00",
                "fim_dia_offset": 1,
            },
            {"dia_semana": 2, "ordem": 1, "inicio": "03:00", "fim": "06:00"},
        ],
    }
    response = requests.post(
        f"{BASE_URL}/api/admin/turnos",
        json=night_payload,
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 201, "overnight_shift")
    night_turn = response.json()["turno"]
    created_turn_ids.append(night_turn["id"])
    if night_turn["periodos"][0]["fim_dia_offset"] != 1:
        raise AssertionError("overnight offset was not preserved")
    response = requests.put(
        f"{BASE_URL}/api/admin/turnos/{night_turn['id']}",
        json={"nome": f"Noturno atualizado {uuid4()}", "periodos": night_payload["periodos"]},
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 200, "unassigned_shift_updated")
    if response.json()["turno"]["periodos"][0]["fim_dia_offset"] != 1:
        raise AssertionError("updated overnight shift lost its day offset")
    response = requests.get(
        f"{BASE_URL}/api/admin/turnos", headers=admin_headers, timeout=20
    )
    expect(response, 200, "company_shifts_listed")
    returned_turn_ids = {item["id"] for item in response.json()["turnos"]}
    if not set(created_turn_ids).issubset(returned_turn_ids):
        raise AssertionError("company shift listing omitted a created shift")

    cross_company_body = {**simple_payload, "nome": f"Inválido {uuid4()}", "empresa_id": company_ids[1]}
    expect(
        requests.post(
            f"{BASE_URL}/api/admin/turnos",
            json=cross_company_body,
            headers=admin_headers,
            timeout=20,
        ),
        403,
        "cross_company_turn_rejected",
    )

    assignment_url = f"{BASE_URL}/api/admin/funcionarios/{employee_ids[1]}/turnos"
    response = requests.post(
        assignment_url,
        json={"turno_id": simple_turn["id"], "vigencia_inicio": "2026-01-01"},
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 201, "first_assignment")
    response = requests.post(
        assignment_url,
        json={"turno_id": multiple_turn["id"], "vigencia_inicio": "2026-02-01"},
        headers=admin_headers,
        timeout=20,
    )
    expect(response, 201, "replacement_assignment")

    response = requests.get(assignment_url, headers=admin_headers, timeout=20)
    expect(response, 200, "assignment_history")
    history = response.json()["historico"]
    if len(history) != 2 or history[0]["vigencia"]["fim"] != "2026-01-31":
        raise AssertionError("assignment history was not preserved correctly")

    admin_journey_url = f"{BASE_URL}/api/admin/funcionarios/{employee_ids[1]}/jornada"
    january = requests.get(
        admin_journey_url,
        params={"data": "2026-01-15"},
        headers=admin_headers,
        timeout=20,
    )
    expect(january, 200, "historical_journey_a")
    if january.json()["jornada"]["turno"]["id"] != simple_turn["id"]:
        raise AssertionError("historical date did not return the first shift")
    february = requests.get(
        admin_journey_url,
        params={"data": "2026-02-15"},
        headers=admin_headers,
        timeout=20,
    )
    expect(february, 200, "historical_journey_b")
    if february.json()["jornada"]["turno"]["id"] != multiple_turn["id"]:
        raise AssertionError("later date did not return the replacement shift")

    own = requests.get(
        f"{BASE_URL}/api/jornada",
        params={"data": date.today().isoformat()},
        headers=employee_headers,
        timeout=20,
    )
    expect(own, 200, "own_journey")
    if own.json()["jornada"]["turno"]["id"] != multiple_turn["id"]:
        raise AssertionError("employee did not receive their own current shift")
    expect(
        requests.get(
            f"{BASE_URL}/api/jornada",
            params={"funcionario_id": employee_ids[2]},
            headers=employee_headers,
            timeout=20,
        ),
        400,
        "own_journey_arbitrary_id_rejected",
    )
    empty = requests.get(
        f"{BASE_URL}/api/jornada", headers=empty_headers, timeout=20
    )
    expect(empty, 200, "employee_without_schedule")
    if empty.json()["jornada"] is not None:
        raise AssertionError("employee without assignment should receive jornada=null")

    expect(
        requests.post(
            f"{BASE_URL}/api/admin/funcionarios/{employee_ids[3]}/turnos",
            json={"turno_id": simple_turn["id"], "vigencia_inicio": "2026-01-01"},
            headers=admin_headers,
            timeout=20,
        ),
        404,
        "foreign_employee_rejected",
    )
    expect(
        requests.post(
            assignment_url,
            json={"turno_id": foreign_turn_id, "vigencia_inicio": "2027-01-01"},
            headers=admin_headers,
            timeout=20,
        ),
        404,
        "foreign_shift_rejected",
    )
    expect(
        requests.put(
            f"{BASE_URL}/api/admin/turnos/{simple_turn['id']}",
            json={"periodos": multiple_payload["periodos"]},
            headers=admin_headers,
            timeout=20,
        ),
        409,
        "assigned_shift_period_change_rejected",
    )
    expect(
        requests.get(
            f"{BASE_URL}/editarHorarios", headers=admin_headers, timeout=20
        ),
        410,
        "legacy_schedule_ui_retired",
    )

    recovery = requests.post(
        f"{BASE_URL}/auth/password/forgot",
        json={"identifier": cpfs[2]},
        headers={"X-Password-Reset-Test-Key": PASSWORD_RESET_TEST_KEY},
        timeout=20,
    )
    expect(recovery, 200, "password_recovery_request")
    recovery_token = recovery.json().get("test_token")
    if not recovery_token:
        raise AssertionError("controlled password recovery did not return a test token")
    expect(
        requests.post(
            f"{BASE_URL}/auth/password/validate",
            json={"token": recovery_token},
            timeout=20,
        ),
        200,
        "password_recovery_token_validated",
    )
    replacement_password = f"Phase8New!{secrets.token_urlsafe(14)}"
    expect(
        requests.post(
            f"{BASE_URL}/auth/password/reset",
            json={"token": recovery_token, "new_password": replacement_password},
            timeout=20,
        ),
        200,
        "password_recovery_completed",
    )
    expect(
        requests.post(
            f"{BASE_URL}/login",
            json={"cpf": cpfs[2], "senha": replacement_password},
            timeout=20,
        ),
        200,
        "password_recovery_new_login",
    )

    logout = requests.post(
        f"{BASE_URL}/auth/logout", headers=admin_headers, timeout=20
    )
    expect(logout, 200, "logout")
    expect(
        requests.get(
            f"{BASE_URL}/api/admin/turnos", headers=admin_headers, timeout=20
        ),
        401,
        "revoked_session_rejected",
    )
    print("phase_8_schedules=ok")
finally:
    cursor.execute(
        "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])", (user_ids,)
    )
    cursor.execute(
        "DELETE FROM password_reset_tokens WHERE usuario_id = ANY(%s::uuid[])",
        (user_ids,),
    )
    cursor.execute(
        "DELETE FROM funcionarios_turnos WHERE funcionario_id = ANY(%s::uuid[])",
        (employee_ids,),
    )
    cursor.execute(
        "DELETE FROM periodos_turno WHERE turno_id = ANY(%s::uuid[])",
        (created_turn_ids + [foreign_turn_id],),
    )
    cursor.execute(
        "DELETE FROM turnos WHERE id = ANY(%s::uuid[])",
        (created_turn_ids + [foreign_turn_id],),
    )
    cursor.execute("DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])", (employee_ids,))
    cursor.execute("DELETE FROM usuarios WHERE id = ANY(%s::uuid[])", (user_ids,))
    cursor.execute("DELETE FROM cargos WHERE id = ANY(%s::uuid[])", (role_ids,))
    cursor.execute("DELETE FROM equipes WHERE id = ANY(%s::uuid[])", (team_ids,))
    cursor.execute("DELETE FROM unidades WHERE id = ANY(%s::uuid[])", (unit_ids,))
    cursor.execute("DELETE FROM empresas WHERE id = ANY(%s::uuid[])", (company_ids,))
    cursor.close()
    connection.close()
