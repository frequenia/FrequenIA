import inspect
import io
import math
import os
import secrets
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD = f"Phase11!{secrets.token_urlsafe(14)}"
MATCH_VECTOR = [1.0] + ([0.0] * 511)
OTHER_VECTOR = [0.0, 1.0] + ([0.0] * 510)


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


def image_form(**extra):
    data = {"imagem": (io.BytesIO(b"controlled-test-image"), "face.png", "image/png")}
    data.update(extra)
    return data


def enrollment_image_form():
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


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def fixture_database():
    connection = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=15)
    connection.autocommit = True
    register_vector(connection)
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    company_ids = [str(uuid4()), str(uuid4())]
    unit_ids = [str(uuid4()), str(uuid4())]
    team_ids = [str(uuid4()), str(uuid4())]
    role_ids = [str(uuid4()), str(uuid4())]
    user_ids = [str(uuid4()) for _ in range(4)]
    employee_ids = [str(uuid4()) for _ in range(4)]
    cpfs = [
        cpf_from_seed(secrets.randbelow(800_000_000) + 100_000_000) for _ in range(4)
    ]
    try:
        for index in range(2):
            cursor.execute(
                "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
                (company_ids[index], f"Fase 11 Empresa {uuid4()}"),
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

        profiles = ["funcionario", "funcionario", "funcionario", "administrador"]
        companies = [0, 0, 1, 0]
        for index, profile in enumerate(profiles):
            company_index = companies[index]
            cursor.execute(
                """
                INSERT INTO usuarios (id, nome, cpf, senha_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_ids[index],
                    f"Fase 11 Usuario {index}",
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
                    f"F11-{uuid4()}",
                    profile,
                ),
            )

        cursor.execute(
            """
            INSERT INTO biometrias (
                empresa_id, funcionario_id, embedding,
                modelo, versao_modelo, status
            ) VALUES
                (%s, %s, %s, 'ArcFace', 'deepface-0.0.99', 'ativa'),
                (%s, %s, %s, 'ArcFace', 'deepface-0.0.99', 'ativa')
            """,
            (
                company_ids[0],
                employee_ids[0],
                MATCH_VECTOR,
                company_ids[1],
                employee_ids[2],
                OTHER_VECTOR,
            ),
        )
        yield cursor, company_ids, user_ids, employee_ids, cpfs
    finally:
        cursor.execute(
            "DELETE FROM auth_sessions WHERE usuario_id = ANY(%s::uuid[])",
            (user_ids,),
        )
        cursor.execute(
            "DELETE FROM tentativas_faciais WHERE funcionario_id = ANY(%s::uuid[])",
            (employee_ids,),
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
import routes.biometrics as biometric_routes
from services.face_service import (
    FaceServiceUnavailableError,
    InvalidFaceCountError,
    InvalidFaceImageError,
)

with fixture_database() as (cursor, company_ids, user_ids, employee_ids, cpfs):
    client = app.app.test_client()
    employee = login(client, cpfs[0])
    no_biometric = login(client, cpfs[1])
    foreign = login(client, cpfs[2])
    admin = login(client, cpfs[3])
    refresh = client.post(
        "/auth/refresh", json={"refresh_token": admin["refresh_token"]}
    )
    expect(refresh, 200, "refresh")
    admin = {**admin, **refresh.get_json()}

    employee_headers = auth_header(employee["access_token"])
    no_biometric_headers = auth_header(no_biometric["access_token"])
    foreign_headers = auth_header(foreign["access_token"])
    admin_headers = auth_header(admin["access_token"])
    verification_url = "/api/biometria/verificar"

    expect(app.app.test_client().post(verification_url), 401, "unauthenticated")
    expect(client.get("/health"), 200, "health")
    expect(client.get("/status"), 200, "status")

    with patch(
        "routes.biometrics.generate_biometric_embedding",
        return_value=MATCH_VECTOR,
    ), patch(
        "routes.biometrics.verify_passive_liveness",
        return_value=(True, 0.99),
    ):
        match = client.post(
            verification_url,
            data=image_form(),
            headers=employee_headers,
        )
    expect(match, 200, "positive_match")
    match_payload = match.get_json()
    if (
        match_payload.get("verificado") is not True
        or match_payload.get("motivo") != "match"
        or not match_payload.get("tentativa_facial_id")
    ):
        raise AssertionError("positive match returned an unexpected contract")
    cursor.execute(
        """
        SELECT id, empresa_id, funcionario_id, resultado, motivo_codigo,
               distancia_facial, instante, created_at
        FROM tentativas_faciais
        WHERE funcionario_id = %s
        ORDER BY instante DESC, id DESC
        LIMIT 1
        """,
        (employee_ids[0],),
    )
    positive_attempt = cursor.fetchone()
    if (
        str(positive_attempt["id"]) != match_payload["tentativa_facial_id"]
        or str(positive_attempt["empresa_id"]) != company_ids[0]
        or str(positive_attempt["funcionario_id"]) != employee_ids[0]
        or positive_attempt["resultado"] != "sucesso"
        or positive_attempt["motivo_codigo"] != "match"
        or not math.isclose(positive_attempt["distancia_facial"], 0.0)
        or positive_attempt["instante"] is None
        or positive_attempt["created_at"] is None
    ):
        raise AssertionError("positive attempt was not persisted correctly")
    print("positive_attempt_persisted=ok")

    # OTHER_VECTOR belongs to a foreign employee. It must not match the authenticated
    # employee, which proves that the route does not identify against global records.
    with patch(
        "routes.biometrics.generate_biometric_embedding",
        return_value=OTHER_VECTOR,
    ), patch(
        "routes.biometrics.verify_passive_liveness",
        return_value=(True, 0.99),
    ):
        no_match = client.post(
            verification_url,
            data=image_form(),
            headers=employee_headers,
        )
    expect(no_match, 200, "negative_match")
    if no_match.get_json() != {
        "verificado": False,
        "motivo": "nao_corresponde",
    }:
        raise AssertionError("negative match returned an unexpected contract")
    cursor.execute(
        """
        SELECT empresa_id, funcionario_id, resultado, motivo_codigo,
               distancia_facial
        FROM tentativas_faciais
        WHERE funcionario_id = %s
        ORDER BY instante DESC, id DESC
        LIMIT 1
        """,
        (employee_ids[0],),
    )
    negative_attempt = cursor.fetchone()
    if (
        str(negative_attempt["empresa_id"]) != company_ids[0]
        or str(negative_attempt["funcionario_id"]) != employee_ids[0]
        or negative_attempt["resultado"] != "falha"
        or negative_attempt["motivo_codigo"] != "nao_corresponde"
        or not math.isclose(negative_attempt["distancia_facial"], 1.0)
    ):
        raise AssertionError("negative attempt was not persisted correctly")
    print("negative_attempt_persisted=ok")

    with patch(
        "routes.biometrics.verify_passive_liveness",
        return_value=(False, 0.95),
    ), patch("routes.biometrics.generate_biometric_embedding") as generate:
        liveness_rejected = client.post(
            verification_url,
            data=image_form(),
            headers=employee_headers,
        )
    expect(liveness_rejected, 200, "liveness_rejected")
    if liveness_rejected.get_json() != {
        "verificado": False,
        "motivo": "liveness_reprovado",
    }:
        raise AssertionError("liveness rejection returned an unexpected contract")
    generate.assert_not_called()
    cursor.execute(
        """
        SELECT resultado, motivo_codigo, distancia_facial
        FROM tentativas_faciais
        WHERE funcionario_id = %s
        ORDER BY instante DESC, id DESC
        LIMIT 1
        """,
        (employee_ids[0],),
    )
    liveness_attempt = cursor.fetchone()
    if liveness_attempt != {
        "resultado": "falha",
        "motivo_codigo": "liveness_reprovado",
        "distancia_facial": None,
    }:
        raise AssertionError("liveness failure was not persisted correctly")
    print("liveness_attempt_persisted=ok")

    expect(
        client.post(verification_url, headers=no_biometric_headers),
        409,
        "missing_biometric",
    )
    cursor.execute(
        """
        SELECT resultado, motivo_codigo, distancia_facial
        FROM tentativas_faciais
        WHERE funcionario_id = %s
        ORDER BY instante DESC, id DESC
        LIMIT 1
        """,
        (employee_ids[1],),
    )
    missing_attempt = cursor.fetchone()
    if missing_attempt != {
        "resultado": "falha",
        "motivo_codigo": "biometria_ausente",
        "distancia_facial": None,
    }:
        raise AssertionError("missing biometric attempt was not persisted correctly")
    print("missing_biometric_attempt_persisted=ok")

    cursor.execute(
        "SELECT count(*) AS total FROM tentativas_faciais WHERE funcionario_id = %s",
        (employee_ids[0],),
    )
    attempts_before_input_errors = cursor.fetchone()["total"]
    expect(
        client.post(verification_url, headers=employee_headers),
        400,
        "missing_image",
    )
    expect(
        client.post(
            verification_url,
            data=image_form(funcionario_id=employee_ids[2]),
            headers=employee_headers,
        ),
        400,
        "client_identity_rejected",
    )
    expect(
        client.post(
            verification_url,
            data=image_form(threshold="2"),
            headers=employee_headers,
        ),
        400,
        "client_threshold_rejected",
    )

    for error, expected, name in (
        (InvalidFaceImageError("Arquivo de imagem invalido."), 400, "invalid_image"),
        (
            InvalidFaceCountError("A imagem deve conter exatamente uma face."),
            422,
            "invalid_face_count",
        ),
        (FaceServiceUnavailableError(), 503, "arcface_unavailable"),
    ):
        with patch(
            "routes.biometrics.generate_biometric_embedding",
            side_effect=error,
        ), patch(
            "routes.biometrics.verify_passive_liveness",
            return_value=(True, 0.99),
        ):
            expect(
                client.post(
                    verification_url,
                    data=image_form(),
                    headers=employee_headers,
                ),
                expected,
                name,
            )
    expect(client.get("/health"), 200, "health_after_arcface_failure")
    cursor.execute(
        "SELECT count(*) AS total FROM tentativas_faciais WHERE funcionario_id = %s",
        (employee_ids[0],),
    )
    if cursor.fetchone()["total"] != attempts_before_input_errors:
        raise AssertionError("an invalid input or technical failure created an attempt")
    print("invalid_and_technical_failures_not_persisted=ok")

    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tentativas_faciais'
        ORDER BY ordinal_position
        """
    )
    attempt_columns = {row["column_name"] for row in cursor.fetchall()}
    if attempt_columns & {"imagem", "embedding", "cpf", "access_token", "refresh_token"}:
        raise AssertionError("facial attempts expose forbidden sensitive columns")
    print("attempt_privacy_columns=ok")

    cursor.execute(
        "UPDATE funcionarios SET status = 'afastado' WHERE id = %s",
        (employee_ids[0],),
    )
    expect(
        client.post(verification_url, headers=employee_headers),
        401,
        "inactive_employee",
    )
    cursor.execute(
        "UPDATE funcionarios SET status = 'ativo' WHERE id = %s",
        (employee_ids[0],),
    )

    cursor.execute(
        "UPDATE empresas SET status = 'inativa' WHERE id = %s", (company_ids[1],)
    )
    expect(
        client.post(verification_url, headers=foreign_headers),
        401,
        "inactive_company",
    )
    cursor.execute(
        "UPDATE empresas SET status = 'ativa' WHERE id = %s", (company_ids[1],)
    )

    revoked = login(client, cpfs[0])
    revoked_headers = auth_header(revoked["access_token"])
    expect(client.post("/auth/logout", headers=revoked_headers), 200, "logout")
    expect(
        client.post(verification_url, headers=revoked_headers),
        401,
        "revoked_session",
    )

    admin_status_url = f"/api/admin/funcionarios/{employee_ids[0]}/biometria"
    expect(client.get(admin_status_url, headers=admin_headers), 200, "admin_status")
    with (
        patch("routes.biometrics.verify_passive_liveness", return_value=(True, 0.9)),
        patch(
            "routes.biometrics.generate_biometric_embedding",
            return_value=MATCH_VECTOR,
        ),
    ):
        expect(
            client.post(
                f"/api/admin/funcionarios/{employee_ids[1]}/biometria",
                data=enrollment_image_form(),
                headers=admin_headers,
            ),
            201,
            "admin_enrollment_regression",
        )
    expect(
        client.post(
            f"/api/admin/funcionarios/{employee_ids[1]}/biometria/revogar",
            headers=admin_headers,
        ),
        200,
        "admin_revocation_regression",
    )

    source = inspect.getsource(biometric_routes._active_biometric)
    required_filters = ("empresa_id = %s", "funcionario_id = %s", "status = 'ativa'")
    if not all(value in source for value in required_filters):
        raise AssertionError("active biometric query is not strictly scoped")
    if "<=>" in source or "<->" in source:
        raise AssertionError("verification query performs facial identification")
    print("strict_one_to_one_query=ok")

print("phase_11_face_verification=ok")
