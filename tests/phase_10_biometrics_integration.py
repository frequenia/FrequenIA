import io
import json
import math
import os
import secrets
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = f"Phase10!{secrets.token_urlsafe(14)}"
VALID_EMBEDDING = [1.0 / math.sqrt(512)] * 512


def expect(response, status, name):
    if response.status_code != status:
        raise AssertionError(
            f"{name}: esperado {status}, obtido {response.status_code}: "
            f"{response.get_data(as_text=True)[:300]}"
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


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def image_form():
    return {
        "imagem": [
            (
                io.BytesIO(b"controlled-test-image"),
                f"face-{index}.png",
                "image/png",
            )
            for index in range(3)
        ]
    }


@contextmanager
def fixture_database():
    connection = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=15)
    connection.autocommit = True
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    company_ids = [str(uuid4()), str(uuid4())]
    unit_ids = [str(uuid4()), str(uuid4())]
    team_ids = [str(uuid4()), str(uuid4())]
    role_ids = [str(uuid4()), str(uuid4())]
    user_ids = [str(uuid4()) for _ in range(3)]
    employee_ids = [str(uuid4()) for _ in range(3)]
    cpfs = [
        cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000) for _ in range(3)
    ]
    try:
        for index in range(2):
            cursor.execute(
                "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
                (company_ids[index], f"Fase 10 Empresa {uuid4()}"),
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
                (
                    team_ids[index],
                    company_ids[index],
                    unit_ids[index],
                    f"Equipe {uuid4()}",
                ),
            )
            cursor.execute(
                "INSERT INTO cargos (id, empresa_id, nome) VALUES (%s, %s, %s)",
                (role_ids[index], company_ids[index], f"Cargo {uuid4()}"),
            )

        profiles = ["administrador", "funcionario", "funcionario"]
        companies = [0, 0, 1]
        for index, profile in enumerate(profiles):
            company_index = companies[index]
            cursor.execute(
                """
                INSERT INTO usuarios (id, nome, cpf, senha_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_ids[index],
                    f"Fase 10 Usuario {index}",
                    cpfs[index],
                    generate_password_hash(PASSWORD),
                ),
            )
            cursor.execute(
                """
                INSERT INTO funcionarios (
                    id, usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                    matricula, perfil, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ativo')
                """,
                (
                    employee_ids[index],
                    user_ids[index],
                    company_ids[company_index],
                    unit_ids[company_index],
                    team_ids[company_index],
                    role_ids[company_index],
                    f"F10-{uuid4()}",
                    profile,
                ),
            )
        yield cursor, company_ids, user_ids, employee_ids, cpfs
    finally:
        cursor.execute(
            "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
            (user_ids,),
        )
        cursor.execute(
            "DELETE FROM biometrias WHERE funcionario_id = ANY(%s::uuid[])",
            (employee_ids,),
        )
        cursor.execute(
            "DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])",
            (employee_ids,),
        )
        cursor.execute("DELETE FROM usuarios WHERE id = ANY(%s::uuid[])", (user_ids,))
        cursor.execute(
            "DELETE FROM equipes WHERE empresa_id = ANY(%s::uuid[])", (company_ids,)
        )
        cursor.execute(
            "DELETE FROM cargos WHERE empresa_id = ANY(%s::uuid[])", (company_ids,)
        )
        cursor.execute(
            "DELETE FROM unidades WHERE empresa_id = ANY(%s::uuid[])", (company_ids,)
        )
        cursor.execute(
            "DELETE FROM empresas WHERE id = ANY(%s::uuid[])", (company_ids,)
        )
        cursor.close()
        connection.close()


def login(client, cpf):
    response = client.post("/login", json={"cpf": cpf, "senha": PASSWORD})
    expect(response, 200, f"login_{cpf[-4:]}")
    return response.get_json()


os.environ.setdefault("APP_ENV", "homologation")
import app
from services.face_service import (
    FaceServiceUnavailableError,
    InvalidFaceCountError,
    InvalidFaceImageError,
)

with fixture_database() as (cursor, company_ids, user_ids, employee_ids, cpfs):
    client = app.app.test_client()
    admin = login(client, cpfs[0])
    refresh = client.post(
        "/auth/refresh", json={"refresh_token": admin["refresh_token"]}
    )
    expect(refresh, 200, "refresh")
    admin = {**admin, **refresh.get_json()}
    employee = login(client, cpfs[1])
    foreign = login(client, cpfs[2])
    admin_headers = auth_header(admin["access_token"])
    employee_headers = auth_header(employee["access_token"])

    own_url = f"/api/admin/funcionarios/{employee_ids[1]}/biometria"
    foreign_url = f"/api/admin/funcionarios/{employee_ids[2]}/biometria"

    expect(client.get("/health"), 200, "health")
    unauthenticated_client = app.app.test_client()
    expect(unauthenticated_client.get(own_url), 401, "unauthenticated_rejected")
    expect(client.get(own_url, headers=employee_headers), 403, "employee_rejected")
    expect(
        client.get(foreign_url, headers=admin_headers), 404, "foreign_company_rejected"
    )
    expect(client.post(own_url, headers=admin_headers), 400, "missing_image_rejected")

    with (
        patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
        patch(
            "routes.biometrics.generate_biometric_embedding",
            side_effect=InvalidFaceImageError("Arquivo de imagem invalido."),
        ),
    ):
        expect(
            client.post(own_url, data=image_form(), headers=admin_headers),
            400,
            "invalid_image_rejected",
        )

    with (
        patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
        patch(
            "routes.biometrics.generate_biometric_embedding",
            side_effect=InvalidFaceCountError(
                "A imagem deve conter exatamente uma face."
            ),
        ),
    ):
        expect(
            client.post(own_url, data=image_form(), headers=admin_headers),
            422,
            "invalid_face_count_rejected",
        )

    with (
        patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
        patch(
            "routes.biometrics.generate_biometric_embedding",
            return_value=VALID_EMBEDDING,
        ),
    ):
        created = client.post(own_url, data=image_form(), headers=admin_headers)
        expect(created, 201, "biometric_enrollment")
        if created.get_json()["recadastro"]:
            raise AssertionError(
                "first enrollment was incorrectly marked as reenrollment"
            )

        reenrolled = client.post(own_url, data=image_form(), headers=admin_headers)
        expect(reenrolled, 201, "biometric_reenrollment")
        if not reenrolled.get_json()["recadastro"]:
            raise AssertionError("reenrollment did not report replacement")

    cursor.execute(
        """
        SELECT status, vector_dims(embedding) AS dimensions,
               referencia_arquivo_privado
        FROM biometrias
        WHERE empresa_id = %s AND funcionario_id = %s
        ORDER BY created_at
        """,
        (company_ids[0], employee_ids[1]),
    )
    stored = cursor.fetchall()
    if len(stored) != 2 or [row["status"] for row in stored].count("ativa") != 1:
        raise AssertionError(
            "reenrollment did not preserve exactly one active biometric"
        )
    if any(row["dimensions"] != 512 for row in stored):
        raise AssertionError("stored embedding has an unexpected dimension")
    if any(row["referencia_arquivo_privado"] is not None for row in stored):
        raise AssertionError("the original image was unexpectedly persisted")
    print("embedding_dimension=512")
    print("reenrollment_history=preserved")

    status = client.get(own_url, headers=admin_headers)
    expect(status, 200, "biometric_status")
    status_text = json.dumps(status.get_json()).lower()
    if "embedding" in status_text or "referencia_arquivo_privado" in status_text:
        raise AssertionError("biometric status exposed sensitive data")
    if status.get_json()["quantidade_total"] != 2:
        raise AssertionError("biometric status returned an incorrect count")

    with (
        patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
        patch(
            "routes.biometrics.generate_biometric_embedding",
            side_effect=FaceServiceUnavailableError(),
        ),
    ):
        expect(
            client.post(own_url, data=image_form(), headers=admin_headers),
            503,
            "arcface_failure_controlled",
        )
    expect(client.get("/health"), 200, "health_after_arcface_failure")

    revoke = client.post(f"{own_url}/revogar", headers=admin_headers)
    expect(revoke, 200, "biometric_revocation")
    if revoke.get_json()["possui_biometria"]:
        raise AssertionError("revocation response still reports an active biometric")

    revoked_login = login(client, cpfs[0])
    revoked_headers = auth_header(revoked_login["access_token"])
    expect(client.post("/auth/logout", headers=revoked_headers), 200, "logout")
    expect(
        client.get(own_url, headers=revoked_headers), 401, "revoked_session_rejected"
    )

    if foreign["access_token"] in status_text:
        raise AssertionError("a token appeared in the biometric response")

print("phase_10_biometrics=ok")
