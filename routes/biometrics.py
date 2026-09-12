"""Cadastro e gestao biometrica administrativa por funcionario_id.

Este modulo nao identifica pessoas por imagem. O funcionario e sempre conhecido
e validado no contexto da empresa autenticada antes da persistencia biometrica.
"""

import logging
import math
from contextlib import closing
from uuid import UUID

import psycopg2.extras
from flask import Blueprint, current_app, g, jsonify, request
from pgvector.psycopg2 import register_vector

from db import conectar_bd
from services.face_service import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    MODEL_VERSION,
    FaceServiceUnavailableError,
    InvalidFaceCountError,
    InvalidFaceImageError,
    LivenessServiceUnavailableError,
    calcular_embedding_medio,
    compare_face_embeddings,
    generate_biometric_embedding,
    verify_passive_liveness,
)
from utils.auth_decorator import require_roles

LOGGER = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MIN_ENROLLMENT_IMAGES = 3
MAX_ENROLLMENT_IMAGES = 5
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

biometrics_bp = Blueprint("biometrics", __name__)


def _uuid(value, field_name):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} invalido.") from exc


def _serialize_biometric(record):
    return {
        "id": str(record["id"]),
        "status": record["status"],
        "modelo": record["modelo"],
        "versao_modelo": record["versao_modelo"],
        "created_at": record["created_at"].isoformat(),
        "updated_at": record["updated_at"].isoformat(),
        "revoked_at": (
            record["revoked_at"].isoformat() if record["revoked_at"] else None
        ),
    }


def _find_employee(cursor, employee_id, company_id, lock=False, active_only=False):
    status_filter = " AND status = 'ativo'" if active_only else ""
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        """
        SELECT id
        FROM funcionarios
        WHERE id = %s AND empresa_id = %s
        """ + status_filter + suffix,
        (employee_id, company_id),
    )
    return cursor.fetchone()


def _employee_exists(employee_id, company_id, active_only=False):
    with closing(conectar_bd()) as connection:
        with connection.cursor() as cursor:
            return bool(
                _find_employee(
                    cursor,
                    employee_id,
                    company_id,
                    active_only=active_only,
                )
            )


def _read_image_uploads():
    if (
        request.content_length is not None
        and request.content_length
        > (MAX_IMAGE_BYTES * MAX_ENROLLMENT_IMAGES) + (256 * 1024)
    ):
        raise ValueError("O conjunto de imagens excede o limite permitido.")
    if request.is_json and "embedding" in (request.get_json(silent=True) or {}):
        raise ValueError("Embedding fornecido pelo cliente nao e aceito.")
    if "embedding" in request.form:
        raise ValueError("Embedding fornecido pelo cliente nao e aceito.")

    uploads = request.files.getlist("imagem")
    if len(uploads) < MIN_ENROLLMENT_IMAGES:
        raise ValueError("Envie no minimo 3 imagens para o cadastro biometrico.")
    if len(uploads) > MAX_ENROLLMENT_IMAGES:
        raise ValueError("Envie no maximo 5 imagens para o cadastro biometrico.")

    imagens = []
    for uploaded in uploads:
        if uploaded.mimetype not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise ValueError("Formato de imagem nao permitido.")
        image_bytes = uploaded.stream.read(MAX_IMAGE_BYTES + 1)
        if not image_bytes:
            raise ValueError("Arquivo de imagem obrigatorio.")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("Cada imagem deve possuir no maximo 5 MiB.")
        imagens.append(image_bytes)
    return imagens


def _read_image_upload():
    """Le uma unica imagem usada pelo reconhecimento 1:1 existente."""
    if (
        request.content_length is not None
        and request.content_length > MAX_IMAGE_BYTES + (64 * 1024)
    ):
        raise ValueError("A imagem excede o limite de 5 MiB.")
    if request.is_json and "embedding" in (request.get_json(silent=True) or {}):
        raise ValueError("Embedding fornecido pelo cliente nao e aceito.")
    if "embedding" in request.form:
        raise ValueError("Embedding fornecido pelo cliente nao e aceito.")

    uploaded = request.files.get("imagem")
    if uploaded is None:
        raise ValueError("Arquivo de imagem obrigatorio.")
    if uploaded.mimetype not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValueError("Formato de imagem nao permitido.")
    image_bytes = uploaded.stream.read(MAX_IMAGE_BYTES + 1)
    if not image_bytes:
        raise ValueError("Arquivo de imagem obrigatorio.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("A imagem excede o limite de 5 MiB.")
    return image_bytes


def _validate_embedding(embedding):
    if (
        not isinstance(embedding, (list, tuple))
        or len(embedding) != EMBEDDING_DIMENSION
    ):
        raise InvalidFaceImageError("A representacao facial gerada e invalida.")
    try:
        numeric = [float(value) for value in embedding]
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidFaceImageError(
            "A representacao facial gerada e invalida."
        ) from exc
    if not all(math.isfinite(value) for value in numeric):
        raise InvalidFaceImageError("A representacao facial gerada e invalida.")
    norm = math.sqrt(sum(value * value for value in numeric))
    if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
        raise InvalidFaceImageError("A representacao facial gerada e invalida.")
    return numeric


def _list_biometrics(employee_id, company_id):
    with closing(conectar_bd()) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if not _find_employee(cursor, employee_id, company_id):
                return None
            cursor.execute(
                """
                SELECT id, status, modelo, versao_modelo,
                       created_at, updated_at, revoked_at
                FROM biometrias
                WHERE empresa_id = %s AND funcionario_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (company_id, employee_id),
            )
            return cursor.fetchall()


@biometrics_bp.get("/api/admin/funcionarios/<funcionario_id>/biometria")
@require_roles("administrador")
def biometric_status(funcionario_id):
    try:
        employee_id = _uuid(funcionario_id, "Funcionario")
        company_id = g.auth_context["empresa_id"]
        records = _list_biometrics(employee_id, company_id)
        if records is None:
            return jsonify({"erro": "Funcionario nao encontrado."}), 404

        serialized = [_serialize_biometric(record) for record in records]
        return (
            jsonify(
                {
                    "funcionario_id": employee_id,
                    "possui_biometria": any(
                        record["status"] == "ativa" for record in records
                    ),
                    "quantidade_total": len(records),
                    "biometrias": serialized,
                }
            ),
            200,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        LOGGER.exception("Falha ao consultar estado biometrico.")
        return jsonify({"erro": "Nao foi possivel consultar a biometria."}), 500


@biometrics_bp.post("/api/admin/funcionarios/<funcionario_id>/biometria")
@require_roles("administrador")
def enroll_biometric(funcionario_id):
    connection = None
    try:
        employee_id = _uuid(funcionario_id, "Funcionario")
        company_id = g.auth_context["empresa_id"]
        if not _employee_exists(employee_id, company_id, active_only=True):
            return jsonify({"erro": "Funcionario nao encontrado."}), 404

        image_uploads = _read_image_uploads()
        embeddings = []
        for image_bytes in image_uploads:
            liveness_approved, _liveness_score = verify_passive_liveness(image_bytes)
            if not liveness_approved:
                return jsonify({"erro": "Liveness reprovado em uma das imagens."}), 422
            embeddings.append(
                _validate_embedding(generate_biometric_embedding(image_bytes))
            )
        embedding = _validate_embedding(calcular_embedding_medio(embeddings))

        connection = conectar_bd()
        register_vector(connection)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if not _find_employee(
                cursor,
                employee_id,
                company_id,
                lock=True,
                active_only=True,
            ):
                connection.rollback()
                return jsonify({"erro": "Funcionario nao encontrado."}), 404

            cursor.execute(
                """
                UPDATE biometrias
                SET status = 'revogada',
                    revoked_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE empresa_id = %s
                  AND funcionario_id = %s
                  AND status = 'ativa'
                """,
                (company_id, employee_id),
            )
            replaced_count = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO biometrias (
                    empresa_id, funcionario_id, embedding,
                    modelo, versao_modelo, referencia_arquivo_privado, status
                )
                VALUES (%s, %s, %s, %s, %s, NULL, 'ativa')
                RETURNING id, status, modelo, versao_modelo,
                          created_at, updated_at, revoked_at
                """,
                (
                    company_id,
                    employee_id,
                    embedding,
                    MODEL_NAME,
                    MODEL_VERSION,
                ),
            )
            record = cursor.fetchone()
        connection.commit()
        return (
            jsonify(
                {
                    "biometria": _serialize_biometric(record),
                    "recadastro": replaced_count > 0,
                }
            ),
            201,
        )
    except InvalidFaceCountError as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc)}), 422
    except InvalidFaceImageError as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except FaceServiceUnavailableError:
        if connection:
            connection.rollback()
        return jsonify({"erro": "Servico facial temporariamente indisponivel."}), 503
    except LivenessServiceUnavailableError:
        if connection:
            connection.rollback()
        return jsonify({"erro": "Servico de liveness temporariamente indisponivel."}), 503
    except ValueError as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        if connection:
            connection.rollback()
        LOGGER.exception("Falha ao cadastrar biometria.")
        return jsonify({"erro": "Nao foi possivel cadastrar a biometria."}), 500
    finally:
        if connection:
            connection.close()


@biometrics_bp.post("/api/admin/funcionarios/<funcionario_id>/biometria/revogar")
@require_roles("administrador")
def revoke_biometric(funcionario_id):
    connection = None
    try:
        employee_id = _uuid(funcionario_id, "Funcionario")
        company_id = g.auth_context["empresa_id"]
        connection = conectar_bd()
        with connection.cursor() as cursor:
            if not _find_employee(cursor, employee_id, company_id, lock=True):
                connection.rollback()
                return jsonify({"erro": "Funcionario nao encontrado."}), 404
            cursor.execute(
                """
                UPDATE biometrias
                SET status = 'revogada',
                    revoked_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE empresa_id = %s
                  AND funcionario_id = %s
                  AND status = 'ativa'
                """,
                (company_id, employee_id),
            )
            revoked_count = cursor.rowcount
        connection.commit()
        return (
            jsonify(
                {
                    "funcionario_id": employee_id,
                    "possui_biometria": False,
                    "revogadas": revoked_count,
                }
            ),
            200,
        )
    except ValueError as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        if connection:
            connection.rollback()
        LOGGER.exception("Falha ao revogar biometria.")
        return jsonify({"erro": "Nao foi possivel revogar a biometria."}), 500
    finally:
        if connection:
            connection.close()


def _reject_verification_authority_fields():
    forbidden = {
        "funcionario_id",
        "usuario_id",
        "cpf",
        "empresa_id",
        "embedding",
        "threshold",
        "limiar",
        "liveness",
        "liveness_ok",
        "is_real",
        "antispoof_score",
    }
    data = request.get_json(silent=True) if request.is_json else None
    if isinstance(data, dict) and any(field in data for field in forbidden):
        raise ValueError("A verificacao nao aceita dados de identidade ou decisao.")
    if any(field in request.form for field in forbidden):
        raise ValueError("A verificacao nao aceita dados de identidade ou decisao.")
    if any(field in request.args for field in forbidden):
        raise ValueError("A verificacao nao aceita dados de identidade ou decisao.")


def _active_biometric(employee_id, company_id):
    with closing(conectar_bd()) as connection:
        register_vector(connection)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT embedding
                FROM biometrias
                WHERE empresa_id = %s
                  AND funcionario_id = %s
                  AND status = 'ativa'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (company_id, employee_id),
            )
            return cursor.fetchone()


def _record_face_attempt(employee_id, company_id, result, reason, distance=None):
    """Persiste somente metadados da tentativa usando o relogio do PostgreSQL."""
    connection = conectar_bd()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tentativas_faciais (
                    empresa_id,
                    funcionario_id,
                    instante,
                    resultado,
                    motivo_codigo,
                    distancia_facial
                )
                VALUES (%s, %s, clock_timestamp(), %s, %s, %s)
                RETURNING id
                """,
                (company_id, employee_id, result, reason, distance),
            )
            attempt_id = cursor.fetchone()[0]
        connection.commit()
        return str(attempt_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@biometrics_bp.post("/api/biometria/verificar")
@require_roles("administrador", "funcionario", "gestor", "rh")
def verify_own_biometric():
    try:
        _reject_verification_authority_fields()
        employee_id = g.auth_funcionario_id
        company_id = g.auth_context["empresa_id"]
        biometric = _active_biometric(employee_id, company_id)
        if not biometric:
            _record_face_attempt(
                employee_id,
                company_id,
                "falha",
                "biometria_ausente",
            )
            return (
                jsonify(
                    {
                        "verificado": False,
                        "motivo": "biometria_ausente",
                    }
                ),
                409,
            )

        image_bytes = _read_image_upload()
        liveness_approved, _liveness_score = verify_passive_liveness(image_bytes)
        if not liveness_approved:
            _record_face_attempt(
                employee_id,
                company_id,
                "falha",
                "liveness_reprovado",
            )
            return (
                jsonify(
                    {
                        "verificado": False,
                        "motivo": "liveness_reprovado",
                    }
                ),
                200,
            )

        candidate = _validate_embedding(generate_biometric_embedding(image_bytes))
        verified, distance = compare_face_embeddings(
            biometric["embedding"],
            candidate,
            current_app.config["FACE_VERIFICATION_MAX_COSINE_DISTANCE"],
        )
        reason = "match" if verified else "nao_corresponde"
        attempt_id = _record_face_attempt(
            employee_id,
            company_id,
            "sucesso" if verified else "falha",
            reason,
            distance,
        )
        payload = {
            "verificado": verified,
            "motivo": reason,
        }
        if verified:
            payload["tentativa_facial_id"] = attempt_id
        return (
            jsonify(payload),
            200,
        )
    except InvalidFaceCountError as exc:
        return jsonify({"erro": str(exc)}), 422
    except InvalidFaceImageError as exc:
        return jsonify({"erro": str(exc)}), 400
    except LivenessServiceUnavailableError:
        return jsonify({"erro": "Servico de liveness temporariamente indisponivel."}), 503
    except FaceServiceUnavailableError:
        return jsonify({"erro": "Servico facial temporariamente indisponivel."}), 503
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        LOGGER.exception("Falha ao verificar biometria 1:1.")
        return jsonify({"erro": "Nao foi possivel verificar a biometria."}), 500
