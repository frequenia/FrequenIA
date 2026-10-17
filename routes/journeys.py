"""APIs da jornada diária, próxima marcação e escalas por data."""

from datetime import date
from uuid import UUID

import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, g, jsonify, request

from db import conectar_bd
from services.daily_journey import JourneyError, resolve_next_event
from services.management_scope import employee_visibility_query
from utils.auth_decorator import require_roles
from utils.schedules import parse_iso_date


journeys_bp = Blueprint("journeys", __name__)


def _uuid(value, label):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} inválido.") from exc


def _engine_options():
    return {
        "default_timezone": current_app.config.get("JOURNEY_DEFAULT_TIMEZONE", "UTC"),
        "grace_hours": current_app.config.get("JOURNEY_OPEN_GRACE_HOURS", 12),
    }


@journeys_bp.get("/api/marcacoes/proxima")
@require_roles("administrador", "funcionario", "gestor", "rh")
def next_personal_marking():
    forbidden = {"empresa_id", "funcionario_id", "usuario_id", "timezone", "tipo", "evento_id", "snapshot_id"}
    if any(name in request.args for name in forbidden):
        return jsonify({"erro": "A consulta pessoal não aceita campos de autoridade."}), 400
    if not g.auth_funcionario_id:
        return jsonify({"erro": "Jornada pessoal não encontrada."}), 404
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            result = resolve_next_event(
                cursor,
                g.auth_context["empresa_id"],
                g.auth_funcionario_id,
                actor_user_id=g.auth_context["user_id"],
                materialize=True,
                **_engine_options(),
            )
        connection.commit()
        return jsonify({"jornada": result}), 200
    except JourneyError as exc:
        connection.rollback()
        return jsonify({"erro": str(exc), "codigo": exc.code}), exc.status
    except Exception:
        connection.rollback()
        current_app.logger.exception("Falha sanitizada no motor de jornada.")
        return jsonify({"erro": "Não foi possível calcular a próxima marcação.", "codigo": "motor_indisponivel"}), 500
    finally:
        connection.close()


def _visible_employee(cursor, employee_id):
    query, params = employee_visibility_query(g.auth_context, employee_id)
    cursor.execute(query, params)
    return bool(cursor.fetchone())


def _serialize_scale(row):
    return {
        "id": str(row["id"]),
        "funcionario_id": str(row["funcionario_id"]),
        "data_operacional": row["data_operacional"].isoformat(),
        "tipo": row["tipo"],
        "origem": row["origem"],
        "turno_id": str(row["turno_id"]) if row["turno_id"] else None,
        "justificativa": row["justificativa"],
        "cancelada": row["cancelado_at"] is not None,
        "created_at": row["created_at"].isoformat(),
        "cancelado_at": row["cancelado_at"].isoformat() if row["cancelado_at"] else None,
    }


@journeys_bp.route("/api/admin/funcionarios/<employee_id>/escalas", methods=["GET", "POST"])
@require_roles("administrador", "rh", "gestor")
def employee_daily_scales(employee_id):
    connection = None
    try:
        employee_id = _uuid(employee_id, "Funcionário")
        if request.args.get("empresa_id") not in (None, ""):
            raise ValueError("A empresa é definida pela autenticação.")
        if request.method == "POST" and g.auth_context["perfil"] == "gestor":
            return jsonify({"erro": "Gestor possui acesso somente de consulta."}), 403
        payload = request.get_json(silent=True) or {}
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if not _visible_employee(cursor, employee_id):
                return jsonify({"erro": "Funcionário não encontrado."}), 404
            if request.method == "GET":
                cursor.execute(
                    """SELECT id,funcionario_id,data_operacional,tipo,origem,turno_id,
                              justificativa,cancelado_at,created_at
                       FROM escalas_diarias WHERE empresa_id=%s AND funcionario_id=%s
                       ORDER BY data_operacional DESC,created_at DESC,id DESC""",
                    (g.auth_context["empresa_id"], employee_id),
                )
                return jsonify({"escalas": [_serialize_scale(row) for row in cursor.fetchall()]}), 200

            allowed = {"data_operacional", "tipo", "origem", "turno_id", "justificativa"}
            if set(payload) - allowed:
                raise ValueError("A requisição contém campos não permitidos.")
            operational_date = parse_iso_date(payload.get("data_operacional"), "Data")
            scale_type = str(payload.get("tipo") or "").strip()
            origin = str(payload.get("origem") or "escala").strip()
            justification = " ".join(str(payload.get("justificativa") or "").split())
            turn_id = _uuid(payload.get("turno_id"), "Turno") if payload.get("turno_id") else None
            if scale_type not in {"turno", "folga"} or origin not in {"escala", "troca", "ajuste"}:
                raise ValueError("Tipo ou origem da escala inválido.")
            if not justification:
                raise ValueError("Justificativa administrativa é obrigatória.")
            if (scale_type == "turno") != bool(turn_id):
                raise ValueError("Escala de turno exige turno; folga não aceita turno.")
            cursor.execute("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date AS hoje")
            if operational_date < cursor.fetchone()["hoje"]:
                return jsonify({"erro": "Escala passada não pode ser reescrita."}), 409
            cursor.execute(
                """SELECT 1 FROM jornadas_diarias
                   WHERE empresa_id=%s AND funcionario_id=%s AND data_operacional=%s""",
                (g.auth_context["empresa_id"], employee_id, operational_date),
            )
            if cursor.fetchone():
                return jsonify({"erro": "A jornada já foi iniciada e seu snapshot é imutável."}), 409
            if turn_id:
                cursor.execute(
                    "SELECT 1 FROM turnos WHERE id=%s AND empresa_id=%s AND status='ativo'",
                    (turn_id, g.auth_context["empresa_id"]),
                )
                if not cursor.fetchone():
                    return jsonify({"erro": "Turno não encontrado."}), 404
            cursor.execute(
                """INSERT INTO escalas_diarias
                   (empresa_id,funcionario_id,data_operacional,tipo,origem,turno_id,
                    justificativa,criado_por_usuario_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,funcionario_id,data_operacional,tipo,origem,turno_id,
                             justificativa,cancelado_at,created_at""",
                (g.auth_context["empresa_id"], employee_id, operational_date, scale_type,
                 origin, turn_id, justification, g.auth_context["user_id"]),
            )
            scale = cursor.fetchone()
            cursor.execute(
                """INSERT INTO auditoria
                   (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
                   VALUES (%s,%s,'escala.diaria_criada','escala_diaria',%s,clock_timestamp(),%s)""",
                (g.auth_context["empresa_id"], g.auth_context["user_id"], scale["id"],
                 psycopg2.extras.Json({"tipo": scale_type, "origem": origin, "data_operacional": operational_date.isoformat()})),
            )
        connection.commit()
        return jsonify({"escala": _serialize_scale(scale)}), 201
    except ValueError as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    except psycopg2.errors.UniqueViolation:
        if connection: connection.rollback()
        return jsonify({"erro": "Já existe escala ativa para essa data."}), 409
    except Exception:
        if connection: connection.rollback()
        current_app.logger.exception("Falha sanitizada ao processar escala diária.")
        return jsonify({"erro": "Não foi possível processar a escala."}), 500
    finally:
        if connection: connection.close()

@journeys_bp.post("/api/admin/escalas/<scale_id>/cancelar")
@require_roles("administrador", "rh")
def cancel_daily_scale(scale_id):
    connection = None
    try:
        scale_id = _uuid(scale_id, "Escala")
        payload = request.get_json(silent=True) or {}
        if set(payload) != {"justificativa"}:
            raise ValueError("Informe somente a justificativa do cancelamento.")
        reason = " ".join(str(payload.get("justificativa") or "").split())
        if not reason:
            raise ValueError("Justificativa do cancelamento é obrigatória.")
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT * FROM escalas_diarias WHERE id=%s AND empresa_id=%s FOR UPDATE""",
                (scale_id, g.auth_context["empresa_id"]),
            )
            scale = cursor.fetchone()
            if not scale:
                return jsonify({"erro": "Escala não encontrada."}), 404
            if scale["cancelado_at"]:
                return jsonify({"escala": _serialize_scale(scale), "reutilizada": True}), 200
            cursor.execute("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date AS hoje")
            if scale["data_operacional"] <= cursor.fetchone()["hoje"]:
                return jsonify({"erro": "Somente escala futura não iniciada pode ser cancelada."}), 409
            cursor.execute(
                """SELECT 1 FROM jornadas_diarias WHERE empresa_id=%s
                   AND funcionario_id=%s AND data_operacional=%s""",
                (g.auth_context["empresa_id"], scale["funcionario_id"], scale["data_operacional"]),
            )
            if cursor.fetchone():
                return jsonify({"erro": "A jornada já possui snapshot imutável."}), 409
            cursor.execute(
                """UPDATE escalas_diarias SET cancelado_at=clock_timestamp(),
                          cancelado_por_usuario_id=%s,cancelamento_justificativa=%s
                   WHERE id=%s RETURNING id,funcionario_id,data_operacional,tipo,origem,
                         turno_id,justificativa,cancelado_at,created_at""",
                (g.auth_context["user_id"], reason, scale_id),
            )
            cancelled = cursor.fetchone()
            cursor.execute(
                """INSERT INTO auditoria
                   (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
                   VALUES (%s,%s,'escala.diaria_cancelada','escala_diaria',%s,clock_timestamp(),%s)""",
                (g.auth_context["empresa_id"], g.auth_context["user_id"], scale_id,
                 psycopg2.extras.Json({"data_operacional": scale["data_operacional"].isoformat()})),
            )
        connection.commit()
        return jsonify({"escala": _serialize_scale(cancelled)}), 200
    except ValueError as exc:
        if connection: connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    finally:
        if connection: connection.close()

