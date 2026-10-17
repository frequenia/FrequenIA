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
from services.facial_failure_occurrences import (
    COUNTED_FAILURE_REASONS,
    consume_facial_failure_cycle,
)
from services.biometric_governance import (
    BiometricGovernanceError,
    create_active_profile,
    create_approved_policy,
    governance_readiness,
    manage_hold,
    record_lifecycle,
    resolve_governance,
    resolve_verification_material,
    transition_biometric,
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
        "estado_transparencia": {
            "ativa": "ativa",
            "bloqueada": "bloqueada",
            "revogada": "recadastro_necessario",
            "exclusao_pendente": "exclusao_pendente",
            "eliminada": "eliminada",
        }.get(record["status"], "indisponivel"),
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

            governance = resolve_governance(cursor, company_id, lock=True)
            if (
                governance.model != MODEL_NAME
                or governance.model_version != MODEL_VERSION
                or governance.dimension != EMBEDDING_DIMENSION
            ):
                raise BiometricGovernanceError(
                    "perfil_biometrico_incompativel",
                    "O perfil tecnico exige recadastro com stack compativel.",
                    409,
                )

            cursor.execute(
                """
                UPDATE biometrias
                SET status = 'revogada',
                    motivo_codigo = 'recadastro',
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
                    modelo, versao_modelo, referencia_arquivo_privado, status,
                    politica_biometrica_id, perfil_tecnico_id
                )
                VALUES (%s, %s, %s, %s, %s, NULL, 'ativa', %s, %s)
                RETURNING id, status, modelo, versao_modelo,
                          created_at, updated_at, revoked_at
                """,
                (
                    company_id,
                    employee_id,
                    embedding,
                    MODEL_NAME,
                    MODEL_VERSION,
                    governance.policy_id,
                    governance.profile_id,
                ),
            )
            record = cursor.fetchone()
            record_lifecycle(
                cursor,
                company_id=company_id,
                employee_id=employee_id,
                biometric_id=record["id"],
                actor_id=g.auth_user_id,
                action="recadastrar" if replaced_count else "cadastrar",
                previous="revogada" if replaced_count else None,
                target="ativa",
                reason="recadastro" if replaced_count else "cadastro_inicial",
                policy_id=governance.policy_id,
                profile_id=governance.profile_id,
            )
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
    except BiometricGovernanceError as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc), "codigo": exc.code}), exc.status
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
    # O resolvedor mantem a consulta estritamente 1:1 com empresa_id = %s,
    # funcionario_id = %s e status = 'ativa'; nunca executa pesquisa vetorial.
    with closing(conectar_bd()) as connection:
        register_vector(connection)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            biometric, governance = resolve_verification_material(
                cursor, company_id, employee_id
            )
            if biometric:
                biometric["limiar"] = governance.threshold
            return biometric


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
            if result == "falha" and reason in COUNTED_FAILURE_REASONS:
                consume_facial_failure_cycle(cursor, company_id, employee_id)
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
            biometric.get(
                "limiar", current_app.config["FACE_VERIFICATION_MAX_COSINE_DISTANCE"]
            ),
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
    except BiometricGovernanceError as exc:
        return jsonify({"verificado": False, "motivo": exc.code}), exc.status
    except Exception:
        LOGGER.exception("Falha ao verificar biometria 1:1.")
        return jsonify({"erro": "Nao foi possivel verificar a biometria."}), 500


@biometrics_bp.get("/api/biometria/estado")
@require_roles("administrador", "funcionario", "gestor", "rh")
def own_biometric_transparency():
    """Transparencia pessoal sem vetor, score ou referencia privada."""
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT b.status,p.versao AS politica_versao,p.versao_aviso,
                          p.finalidade,p.canal_atendimento,p.retencao_dias
                   FROM funcionarios f
                   LEFT JOIN biometrias b ON b.empresa_id=f.empresa_id
                    AND b.funcionario_id=f.id
                   LEFT JOIN politicas_biometricas p ON p.empresa_id=b.empresa_id
                    AND p.id=b.politica_biometrica_id
                   WHERE f.empresa_id=%s AND f.id=%s
                   ORDER BY b.created_at DESC,b.id DESC LIMIT 1""",
                (g.auth_context["empresa_id"], g.auth_funcionario_id),
            )
            row = cursor.fetchone()
        if not row:
            return jsonify({"erro": "Funcionario nao encontrado."}), 404
        status = row["status"] or "recadastro_necessario"
        return jsonify({
            "estado": {"revogada": "recadastro_necessario"}.get(status, status),
            "politica": ({
                "versao": row["politica_versao"], "versao_aviso": row["versao_aviso"],
                "finalidade": row["finalidade"], "canal_atendimento": row["canal_atendimento"],
                "retencao_dias": row["retencao_dias"],
            } if row["politica_versao"] else None),
            "explicacao": (
                "Verificacao facial 1:1 para registro de ponto; nao realiza pesquisa facial global. "
                "As fotos enviadas sao processadas em memoria e nao sao persistidas pelo fluxo atual."
            ),
        }), 200
    finally:
        connection.close()


@biometrics_bp.post("/api/admin/funcionarios/<funcionario_id>/biometria/ciclo")
@require_roles("administrador", "rh")
def mutate_biometric_lifecycle(funcionario_id):
    connection = None
    try:
        payload = request.get_json(silent=True) or {}
        allowed = {"operacao", "motivo", "idempotencia", "referencia", "expira_at"}
        if not set(payload).issubset(allowed) or not {"operacao", "motivo", "idempotencia"}.issubset(payload):
            raise ValueError("Informe operacao, motivo e idempotencia.")
        company_id = g.auth_context["empresa_id"]
        employee_id = _uuid(funcionario_id, "Funcionario")
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if not _find_employee(cursor, employee_id, company_id, lock=True):
                connection.rollback()
                return jsonify({"erro": "Funcionario nao encontrado."}), 404
            if payload["operacao"] in {"criar_hold", "cancelar_hold"}:
                result = manage_hold(
                    cursor, company_id=company_id, employee_id=employee_id,
                    actor_id=g.auth_user_id, operation=payload["operacao"],
                    reason=payload["motivo"], reference=payload.get("referencia"),
                    idempotency_key=payload["idempotencia"], expires_at=payload.get("expira_at"),
                )
            else:
                result = transition_biometric(
                    cursor, company_id=company_id, employee_id=employee_id,
                    actor_id=g.auth_user_id, operation=payload["operacao"],
                    reason=payload["motivo"], idempotency_key=payload["idempotencia"],
                )
        connection.commit()
        return jsonify(result), 200
    except (ValueError, BiometricGovernanceError) as exc:
        if connection:
            connection.rollback()
        status = exc.status if isinstance(exc, BiometricGovernanceError) else 400
        code = exc.code if isinstance(exc, BiometricGovernanceError) else "requisicao_invalida"
        return jsonify({"erro": str(exc), "codigo": code}), status
    finally:
        if connection:
            connection.close()


@biometrics_bp.get("/api/admin/governanca-biometrica/readiness")
@require_roles("administrador", "rh")
def biometric_governance_readiness():
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            state = governance_readiness(cursor, g.auth_context["empresa_id"])
        return jsonify({"status": "ready" if all(state.values()) else "not_ready", "dependencies": state}), (200 if all(state.values()) else 503)
    finally:
        connection.close()


def _serialize_governance_row(row):
    return {
        key: (str(value) if key == "id" else float(value) if key == "limiar" else value)
        for key, value in row.items()
    }


@biometrics_bp.post("/api/admin/governanca-biometrica/politicas")
@require_roles("administrador", "rh")
def approve_biometric_policy():
    connection = None
    try:
        payload = request.get_json(silent=True) or {}
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            row = create_approved_policy(
                cursor, company_id=g.auth_context["empresa_id"],
                actor_id=g.auth_user_id, payload=payload,
            )
        connection.commit()
        return jsonify({"politica": _serialize_governance_row(row)}), 201
    except (BiometricGovernanceError, psycopg2.Error) as exc:
        if connection: connection.rollback()
        code = exc.code if isinstance(exc, BiometricGovernanceError) else "politica_conflitante"
        status = exc.status if isinstance(exc, BiometricGovernanceError) else 409
        return jsonify({"erro": "Politica biometrica invalida ou conflitante.", "codigo": code}), status
    finally:
        if connection: connection.close()


@biometrics_bp.post("/api/admin/governanca-biometrica/perfis")
@require_roles("administrador", "rh")
def activate_biometric_profile():
    connection = None
    try:
        payload = request.get_json(silent=True) or {}
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            row = create_active_profile(
                cursor, company_id=g.auth_context["empresa_id"],
                actor_id=g.auth_user_id, payload=payload,
            )
        connection.commit()
        return jsonify({"perfil": _serialize_governance_row(row)}), 201
    except (BiometricGovernanceError, psycopg2.Error) as exc:
        if connection: connection.rollback()
        code = exc.code if isinstance(exc, BiometricGovernanceError) else "perfil_conflitante"
        status = exc.status if isinstance(exc, BiometricGovernanceError) else 409
        return jsonify({"erro": "Perfil tecnico invalido ou conflitante.", "codigo": code}), status
    finally:
        if connection: connection.close()
