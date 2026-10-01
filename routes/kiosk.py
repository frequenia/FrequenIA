"""Quiosque de ponto: matrícula restrita ao terminal e biometria 1:1."""

import hashlib
import logging
import math
import secrets
from uuid import UUID, uuid4

import psycopg2.extras
from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for
from pgvector.psycopg2 import register_vector

from db import conectar_bd
from routes.biometrics import (
    _read_image_upload,
    _validate_embedding,
    verify_passive_liveness,
    generate_biometric_embedding,
    compare_face_embeddings,
)
from routes.views import (
    ALLOWED_CLOCK_EVENT_TYPES,
    bloquear_funcionario_para_marcacao,
    buscar_marcacao_por_idempotencia,
    buscar_marcacao_recente,
    chave_idempotencia_requisicao,
    resposta_marcacao_recente,
    serializar_marcacao,
)
from services.face_service import FaceServiceUnavailableError, InvalidFaceCountError, InvalidFaceImageError, LivenessServiceUnavailableError
from services.facial_failure_occurrences import (
    COUNTED_FAILURE_REASONS,
    consume_facial_failure_cycle,
)
from utils.auth_decorator import require_roles
from utils.terminal_auth import terminal_required

LOGGER = logging.getLogger(__name__)
kiosk_bp = Blueprint("kiosk", __name__)


def _credential_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _uuid(value, field):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} inválido.") from exc


def _terminal_payload():
    data = request.get_json(silent=True) or {}
    name = data.get("nome")
    if set(data) != {"nome"} or not isinstance(name, str) or not 0 < len(name.strip()) <= 120:
        raise ValueError("Informe somente o nome do terminal.")
    return name.strip()


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@kiosk_bp.get("/admin/terminais-ponto")
@require_roles("administrador")
def terminal_management_page():
    return _no_store(current_app.make_response(render_template("terminaisPonto.html")))


@kiosk_bp.get("/api/admin/terminais-ponto")
@require_roles("administrador")
def list_terminals():
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT id, nome, status, created_at, revoked_at
                   FROM terminais_ponto WHERE empresa_id=%s
                   ORDER BY created_at DESC, id DESC""",
                (g.auth_context["empresa_id"],),
            )
            terminals = cursor.fetchall()
        return _no_store(jsonify({"terminais": [
            {
                "id": str(item["id"]),
                "nome": item["nome"],
                "status": item["status"],
                "created_at": item["created_at"].isoformat(),
                "revoked_at": item["revoked_at"].isoformat() if item["revoked_at"] else None,
            }
            for item in terminals
        ]}))
    finally:
        connection.close()


@kiosk_bp.post("/api/admin/terminais-ponto")
@require_roles("administrador")
def provision_terminal():
    connection = None
    try:
        name = _terminal_payload()
        credential = secrets.token_urlsafe(32)
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """INSERT INTO terminais_ponto (empresa_id, nome, credencial_hash)
                   VALUES (%s, %s, %s) RETURNING id, nome, status, created_at""",
                (g.auth_context["empresa_id"], name, _credential_hash(credential)),
            )
            terminal = cursor.fetchone()
        connection.commit()
        serialized = {
            key: str(value) if key == "id" else value
            for key, value in terminal.items()
        }
        serialized["credencial"] = credential
        return _no_store(jsonify({"terminal": serialized})), 201
    except ValueError as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        if connection: connection.rollback()
        LOGGER.exception("Falha ao provisionar terminal.")
        return jsonify({"erro": "Não foi possível provisionar o terminal."}), 500
    finally:
        if connection: connection.close()


@kiosk_bp.post("/api/admin/terminais-ponto/<terminal_id>/revogar")
@require_roles("administrador")
def revoke_terminal(terminal_id):
    connection = None
    try:
        connection = conectar_bd()
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE terminais_ponto SET status='revogado', revoked_at=clock_timestamp()
                   WHERE id=%s AND empresa_id=%s AND status='ativo' RETURNING id""",
                (_uuid(terminal_id, "Terminal"), g.auth_context["empresa_id"]),
            )
            revoked = cursor.fetchone()
        connection.commit()
        if not revoked: return jsonify({"erro": "Terminal não encontrado."}), 404
        return jsonify({"terminal_id": str(revoked[0]), "status": "revogado"}), 200
    except ValueError as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        if connection: connection.rollback()
        return jsonify({"erro": "Não foi possível revogar o terminal."}), 500
    finally:
        if connection: connection.close()


@kiosk_bp.post("/api/quiosque/ativar")
def activate_terminal():
    data = request.get_json(silent=True) or {}
    credential = data.get("credencial") if set(data) == {"credencial"} else None
    if not isinstance(credential, str) or not 32 <= len(credential) <= 256:
        return jsonify({"erro": "Credencial de terminal inválida."}), 401
    connection = conectar_bd()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id FROM terminais_ponto WHERE credencial_hash=%s
                   AND status='ativo' AND revoked_at IS NULL""",
                (_credential_hash(credential),),
            )
            terminal = cursor.fetchone()
    finally:
        connection.close()
    if not terminal:
        return jsonify({"erro": "Credencial de terminal inválida."}), 401
    session.clear()
    session.permanent = True
    session["terminal_ponto_id"] = str(terminal[0])
    return _no_store(current_app.make_response(("", 204)))


@kiosk_bp.get("/quiosque/ativar")
def activation_page():
    terminal_id = session.get("terminal_ponto_id")
    if terminal_id:
        try:
            terminal_id = str(UUID(str(terminal_id)))
        except (TypeError, ValueError, AttributeError):
            session.pop("terminal_ponto_id", None)
        else:
            connection = conectar_bd()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT 1 FROM terminais_ponto WHERE id=%s
                           AND status='ativo' AND revoked_at IS NULL""",
                        (terminal_id,),
                    )
                    if cursor.fetchone():
                        return redirect(url_for("kiosk.kiosk_page"))
            finally:
                connection.close()
            session.pop("terminal_ponto_id", None)
    return _no_store(current_app.make_response(render_template("ativarTerminal.html")))


@kiosk_bp.get("/quiosque/ponto")
@terminal_required
def kiosk_page():
    return render_template("reconhecimentoFacial.html")


def _find_employee_by_registration(cursor, company_id, registration):
    cursor.execute(
        """SELECT id FROM funcionarios WHERE empresa_id=%s AND matricula=%s
           AND status='ativo' FOR UPDATE""",
        (company_id, registration),
    )
    return cursor.fetchone()


def _active_biometric(cursor, company_id, employee_id):
    cursor.execute(
        """SELECT embedding FROM biometrias WHERE empresa_id=%s AND funcionario_id=%s
           AND status='ativa' ORDER BY created_at DESC, id DESC LIMIT 1 FOR SHARE""",
        (company_id, employee_id),
    )
    return cursor.fetchone()


def _record_attempt(cursor, company_id, employee_id, result, reason, distance=None):
    cursor.execute(
        """INSERT INTO tentativas_faciais
           (empresa_id, funcionario_id, instante, resultado, motivo_codigo, distancia_facial)
           VALUES (%s, %s, clock_timestamp(), %s, %s, %s) RETURNING id""",
        (company_id, employee_id, result, reason, distance),
    )
    attempt_id = str(cursor.fetchone()[0])
    if result == "falha" and reason in COUNTED_FAILURE_REASONS:
        consume_facial_failure_cycle(cursor, company_id, employee_id)
    return attempt_id


@kiosk_bp.post("/api/quiosque/marcacoes/facial")
@terminal_required
def create_kiosk_facial_clock():
    connection = None
    try:
        if any(field in request.form or field in request.args for field in ("empresa_id", "funcionario_id", "usuario_id", "embedding", "tentativa_facial_id")):
            raise ValueError("A requisição contém campos controlados pelo servidor.")
        registration = str(request.form.get("matricula") or "").strip()
        clock_type = str(request.form.get("tipo") or "").strip()
        if not registration or len(registration) > 128: raise ValueError("Matrícula inválida.")
        if clock_type not in ALLOWED_CLOCK_EVENT_TYPES: raise ValueError("Tipo de marcação inválido.")
        image = _read_image_upload()
        key = chave_idempotencia_requisicao()
        company_id = g.terminal_context["empresa_id"]
        connection = conectar_bd(); register_vector(connection)
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        employee = _find_employee_by_registration(cursor, company_id, registration)
        if not employee:
            connection.rollback(); return jsonify({"erro": "Funcionário não encontrado."}), 404
        employee_id = str(employee["id"])
        bloquear_funcionario_para_marcacao(cursor, company_id, employee_id)
        existing = buscar_marcacao_por_idempotencia(cursor, company_id, key)
        if existing:
            connection.rollback()
            if str(existing["funcionario_id"]) != employee_id or existing["origem"] != "facial":
                return jsonify({"erro": "Chave de idempotência indisponível."}), 409
            return jsonify({"marcacao": serializar_marcacao(existing), "reutilizada": True}), 200
        biometric = _active_biometric(cursor, company_id, employee_id)
        if not biometric:
            _record_attempt(cursor, company_id, employee_id, "falha", "biometria_ausente")
            connection.commit(); return jsonify({"verificado": False, "erro": "Não foi possível concluir a verificação."}), 409
        approved, _score = verify_passive_liveness(image)
        if not approved:
            _record_attempt(cursor, company_id, employee_id, "falha", "liveness_reprovado")
            connection.commit(); return jsonify({"verificado": False, "erro": "Não foi possível concluir a verificação."}), 422
        candidate = _validate_embedding(generate_biometric_embedding(image))
        verified, distance = compare_face_embeddings(biometric["embedding"], candidate, current_app.config["FACE_VERIFICATION_MAX_COSINE_DISTANCE"])
        if not verified:
            _record_attempt(cursor, company_id, employee_id, "falha", "nao_corresponde", distance)
            connection.commit(); return jsonify({"verificado": False, "erro": "Não foi possível concluir a verificação."}), 409
        recent = buscar_marcacao_recente(cursor, company_id, employee_id)
        if recent:
            connection.rollback(); return resposta_marcacao_recente(recent)
        attempt_id = _record_attempt(cursor, company_id, employee_id, "sucesso", "match", distance)
        cursor.execute(
            """INSERT INTO marcacoes (empresa_id, funcionario_id, tentativa_facial_id,
               instante, tipo, origem, estado, chave_idempotencia)
               VALUES (%s, %s, %s, clock_timestamp(), %s, 'facial', 'confirmada', %s)
               RETURNING id, tentativa_facial_id, tipo, origem, estado, instante, chave_idempotencia""",
            (company_id, employee_id, attempt_id, clock_type, key),
        )
        marking = cursor.fetchone(); connection.commit()
        return jsonify({"marcacao": serializar_marcacao(marking)}), 201
    except (InvalidFaceCountError, InvalidFaceImageError) as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 422
    except LivenessServiceUnavailableError:
        if connection: connection.rollback()
        return jsonify({"erro": "Serviço de liveness temporariamente indisponível."}), 503
    except FaceServiceUnavailableError:
        if connection: connection.rollback()
        return jsonify({"erro": "Serviço facial temporariamente indisponível."}), 503
    except ValueError as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except psycopg2.errors.UniqueViolation:
        if connection: connection.rollback()
        return jsonify({"erro": "Não foi possível repetir esta marcação."}), 409
    except Exception:
        if connection: connection.rollback()
        LOGGER.exception("Falha ao registrar ponto no quiosque.")
        return jsonify({"erro": "Não foi possível registrar o ponto."}), 500
    finally:
        if connection: connection.close()
