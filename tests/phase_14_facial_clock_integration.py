import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import psycopg2
import psycopg2.extras
import requests
from werkzeug.security import generate_password_hash


BASE_URL = os.getenv("PHASE14_BASE_URL", "http://127.0.0.1:5000")
DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = f"Phase14!{secrets.token_urlsafe(14)}"


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


def auth_headers(token, idempotency_key=None):
    result = {"Authorization": f"Bearer {token}"}
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


def facial_clock(token, attempt_id, key=None, clock_type="entrada"):
    return requests.post(
        f"{BASE_URL}/api/marcacoes/facial",
        json={"tipo": clock_type, "tentativa_facial_id": attempt_id},
        headers=auth_headers(token, key),
        timeout=30,
    )


connection = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=15)
connection.autocommit = True
cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

company_ids = [str(uuid4()), str(uuid4())]
unit_ids = [str(uuid4()), str(uuid4())]
team_ids = [str(uuid4()), str(uuid4())]
role_ids = [str(uuid4()), str(uuid4())]
user_ids = [str(uuid4()) for _ in range(5)]
employee_ids = [str(uuid4()) for _ in range(5)]
cpfs = [cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000) for _ in range(5)]
attempt_ids = []
clock_ids = []


def create_attempt(employee_index, result="sucesso", reason="match", age_seconds=0):
    attempt_id = str(uuid4())
    attempt_ids.append(attempt_id)
    company_index = 1 if employee_index == 4 else 0
    cursor.execute(
        """
        INSERT INTO tentativas_faciais (
            id, empresa_id, funcionario_id, instante, resultado,
            motivo_codigo, distancia_facial
        )
        VALUES (
            %s, %s, %s,
            clock_timestamp() - (%s * interval '1 second'),
            %s, %s, %s
        )
        """,
        (
            attempt_id,
            company_ids[company_index],
            employee_ids[employee_index],
            age_seconds,
            result,
            reason,
            0.12 if reason == "match" else None,
        ),
    )
    return attempt_id


try:
    for index in range(2):
        cursor.execute(
            "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
            (company_ids[index], f"Fase 14 Empresa {uuid4()}"),
        )
        cursor.execute(
            "INSERT INTO unidades (id, empresa_id, nome) VALUES (%s, %s, %s)",
            (unit_ids[index], company_ids[index], f"Unidade {uuid4()}"),
        )
        cursor.execute(
            "INSERT INTO equipes (id, empresa_id, unidade_id, nome) VALUES (%s, %s, %s, %s)",
            (team_ids[index], company_ids[index], unit_ids[index], f"Equipe {uuid4()}"),
        )
        cursor.execute(
            "INSERT INTO cargos (id, empresa_id, nome) VALUES (%s, %s, %s)",
            (role_ids[index], company_ids[index], f"Cargo {uuid4()}"),
        )

    for index in range(5):
        company_index = 1 if index == 4 else 0
        cursor.execute(
            "INSERT INTO usuarios (id, nome, cpf, senha_hash) VALUES (%s, %s, %s, %s)",
            (
                user_ids[index],
                f"Fase 14 Usuário {index}",
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'funcionario', 'ativo')
            """,
            (
                employee_ids[index],
                user_ids[index],
                company_ids[company_index],
                unit_ids[company_index],
                team_ids[company_index],
                role_ids[company_index],
                f"F14-{uuid4()}",
            ),
        )

    tokens = []
    for index, cpf in enumerate(cpfs):
        response = requests.post(
            f"{BASE_URL}/login",
            json={"cpf": cpf, "senha": PASSWORD},
            timeout=30,
        )
        expect(response, 200, f"login_fixture_{index}")
        tokens.append(response.json()["access_token"])

    valid = create_attempt(0)
    non_match = create_attempt(0, "falha", "nao_corresponde")
    liveness_failed = create_attempt(0, "falha", "liveness_reprovado")
    biometric_missing = create_attempt(0, "falha", "biometria_ausente")
    expired = create_attempt(0, age_seconds=121)
    other_employee = create_attempt(1)
    foreign_company = create_attempt(4)

    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes/facial",
            json={"tipo": "entrada", "tentativa_facial_id": valid},
            timeout=20,
        ),
        401,
        "unauthenticated_rejected",
    )
    expect(
        requests.post(
            f"{BASE_URL}/api/marcacoes/facial",
            json={
                "tipo": "entrada",
                "tentativa_facial_id": valid,
                "funcionario_id": employee_ids[1],
            },
            headers=auth_headers(tokens[0]),
            timeout=20,
        ),
        400,
        "client_identity_rejected",
    )
    expect(
        facial_clock(tokens[0], str(uuid4())),
        404,
        "missing_attempt_rejected",
    )
    expect(facial_clock(tokens[0], other_employee), 404, "other_employee_rejected")
    expect(facial_clock(tokens[0], foreign_company), 404, "foreign_company_rejected")
    expect(facial_clock(tokens[0], non_match), 409, "non_match_rejected")
    expect(facial_clock(tokens[0], liveness_failed), 409, "liveness_rejected")
    expect(facial_clock(tokens[0], biometric_missing), 409, "missing_biometric_rejected")
    expect(facial_clock(tokens[0], expired), 409, "expired_attempt_rejected")

    idempotency_key = str(uuid4())
    created_response = facial_clock(tokens[0], valid, idempotency_key)
    expect(created_response, 201, "facial_clock_created")
    created = created_response.json()["marcacao"]
    clock_ids.append(created["id"])
    if (
        created["tentativa_facial_id"] != valid
        or created["origem"] != "facial"
        or created["estado"] != "confirmada"
    ):
        raise AssertionError("facial clock response has incorrect server values")
    if datetime.fromisoformat(created["instante"]).tzinfo is None:
        raise AssertionError("facial clock timestamp is not timezone-aware")

    cursor.execute(
        """
        SELECT empresa_id, funcionario_id, tentativa_facial_id, origem, estado,
               instante <= clock_timestamp() AS timestamp_from_database
        FROM marcacoes WHERE id = %s
        """,
        (created["id"],),
    )
    stored = cursor.fetchone()
    if (
        str(stored["empresa_id"]) != company_ids[0]
        or str(stored["funcionario_id"]) != employee_ids[0]
        or str(stored["tentativa_facial_id"]) != valid
        or stored["origem"] != "facial"
        or stored["estado"] != "confirmada"
        or not stored["timestamp_from_database"]
    ):
        raise AssertionError("facial clock was not persisted with authenticated identity")
    print("facial_clock_database_link=ok")

    repeated = facial_clock(tokens[0], valid, idempotency_key)
    expect(repeated, 200, "idempotent_retry")
    if repeated.json()["marcacao"]["id"] != created["id"]:
        raise AssertionError("idempotent retry did not return original marking")
    expect(
        facial_clock(tokens[0], valid, str(uuid4())),
        409,
        "attempt_reuse_rejected",
    )

    conflicting_attempt = create_attempt(0)
    expect(
        facial_clock(tokens[0], conflicting_attempt, idempotency_key),
        409,
        "idempotency_conflict_rejected",
    )
    expect(
        facial_clock(tokens[0], conflicting_attempt, str(uuid4())),
        409,
        "temporal_duplicate_preserved",
    )

    concurrent_attempt = create_attempt(2)

    def concurrent_request(key):
        return facial_clock(tokens[2], concurrent_attempt, key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent = list(
            executor.map(concurrent_request, [str(uuid4()), str(uuid4())])
        )
    statuses = sorted(response.status_code for response in concurrent)
    if statuses != [201, 409]:
        raise AssertionError(f"concurrent facial marking returned {statuses}")
    concurrent_created = next(
        response for response in concurrent if response.status_code == 201
    ).json()["marcacao"]
    clock_ids.append(concurrent_created["id"])
    cursor.execute(
        "SELECT count(*) AS total FROM marcacoes WHERE tentativa_facial_id = %s",
        (concurrent_attempt,),
    )
    if cursor.fetchone()["total"] != 1:
        raise AssertionError("concurrent requests consumed an attempt more than once")
    print("concurrent_attempt_consumption=201,409")

    manual_key = str(uuid4())
    manual = requests.post(
        f"{BASE_URL}/api/marcacoes",
        json={"tipo": "entrada"},
        headers=auth_headers(tokens[3], manual_key),
        timeout=20,
    )
    expect(manual, 201, "manual_clock_regression")
    manual_row = manual.json()["marcacao"]
    clock_ids.append(manual_row["id"])
    if manual_row["origem"] != "manual" or "tentativa_facial_id" in manual_row:
        raise AssertionError("manual clock behavior changed")

    print("phase_14_facial_clock=ok")
finally:
    cursor.execute(
        "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
        (user_ids,),
    )
    cursor.execute(
        "DELETE FROM marcacoes WHERE id = ANY(%s::uuid[])",
        (clock_ids,),
    )
    cursor.execute(
        "DELETE FROM marcacoes WHERE tentativa_facial_id = ANY(%s::uuid[])",
        (attempt_ids,),
    )
    cursor.execute(
        "DELETE FROM tentativas_faciais WHERE id = ANY(%s::uuid[])",
        (attempt_ids,),
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
