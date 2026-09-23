"""Solicitações pessoais e análise auditável de correções de ponto."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg2.extras
from flask import Blueprint, g, jsonify, render_template, request

from db import conectar_bd
from utils.auth_decorator import access_token_required, require_roles

occurrences_bp = Blueprint("occurrences", __name__)
MANAGEMENT_ROLES = ("administrador", "gestor", "rh")
CATEGORIES = {
    "esquecimento_marcacao": "inclusao",
    "horario_incorreto": "alteracao_instante",
    "tipo_incorreto": "alteracao_tipo",
    "justificativa": "justificativa",
}
CLOCK_TYPES = {"entrada", "saida_intervalo", "retorno_intervalo", "saida"}
PENDING_DB = "solicitada"
STATUS_TO_DB = {"pendente": "solicitada", "aprovada": "aprovada", "rejeitada": "rejeitada", "cancelada": "cancelada"}
DB_TO_STATUS = {value: key for key, value in STATUS_TO_DB.items()}
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
CLIENT_FIELDS = {"tipo", "marcacao_id", "motivo", "instante_solicitado", "tipo_marcacao_solicitado"}
SERVER_FIELDS = {"empresa_id", "funcionario_id", "usuario_id", "estado", "status", "analisado_por", "responsavel_decisao_usuario_id", "decisao", "decided_at"}


def _uuid(value, label):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} inválido.") from exc


def _aware_datetime(value):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Instante solicitado inválido.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Instante solicitado deve incluir timezone ou Z.")
    return parsed.astimezone(timezone.utc)


def _date(value, label):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{label} inválida.") from exc


def _utc_bounds(start, end):
    start_utc = datetime.combine(start, time.min, LOCAL_TIMEZONE).astimezone(timezone.utc) if start else None
    end_utc = datetime.combine(end + timedelta(days=1), time.min, LOCAL_TIMEZONE).astimezone(timezone.utc) if end else None
    return start_utc, end_utc


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("JSON inválido.")
    forbidden = (set(data) & SERVER_FIELDS) | (set(data) - CLIENT_FIELDS)
    if forbidden:
        raise ValueError("O payload contém campos controlados pelo servidor.")
    return data


def _validate_request(data):
    category = str(data.get("tipo") or "").strip()
    if category not in {*CATEGORIES, "outro"}:
        raise ValueError("Tipo de ocorrência inválido.")
    reason = str(data.get("motivo") or "").strip()
    if not reason:
        raise ValueError("Motivo é obrigatório.")
    marking_id = _uuid(data["marcacao_id"], "Marcação") if data.get("marcacao_id") else None
    proposed_instant = _aware_datetime(data.get("instante_solicitado"))
    proposed_type = str(data.get("tipo_marcacao_solicitado") or "").strip() or None
    if proposed_type and proposed_type not in CLOCK_TYPES:
        raise ValueError("Tipo de marcação solicitado inválido.")

    if category == "esquecimento_marcacao":
        if marking_id or not proposed_instant or not proposed_type:
            raise ValueError("Esquecimento exige instante e tipo, sem marcação original.")
        operation = "inclusao"
    elif category == "horario_incorreto":
        if not marking_id or not proposed_instant:
            raise ValueError("Horário incorreto exige marcação e instante solicitado.")
        if proposed_type:
            raise ValueError("Horário incorreto não aceita tipo de marcação solicitado.")
        operation = "alteracao_instante"
    elif category == "tipo_incorreto":
        if not marking_id or not proposed_type:
            raise ValueError("Tipo incorreto exige marcação e tipo solicitado.")
        if proposed_instant:
            raise ValueError("Tipo incorreto não aceita instante solicitado.")
        operation = "alteracao_tipo"
    elif category == "justificativa":
        if proposed_instant or proposed_type:
            raise ValueError("Justificativa não altera horário ou tipo.")
        operation = "justificativa"
    else:
        if proposed_instant and proposed_type and not marking_id:
            operation = "inclusao"
        elif proposed_instant and marking_id and not proposed_type:
            operation = "alteracao_instante"
        elif proposed_type and marking_id and not proposed_instant:
            operation = "alteracao_tipo"
        elif not proposed_instant and not proposed_type:
            operation = "justificativa"
        else:
            raise ValueError("Combinação de campos inválida para outro tipo.")
    return category, operation, marking_id, reason, proposed_instant, proposed_type


def _serialize(row):
    def iso(value):
        return value.isoformat() if value else None

    return {
        "id": str(row["id"]),
        "tipo": row["categoria"],
        "status": DB_TO_STATUS.get(row["estado"], row["estado"]),
        "motivo": row["motivo"],
        "marcacao_id": str(row["marcacao_original_id"]) if row.get("marcacao_original_id") else None,
        "instante_original": iso(row.get("instante_original")),
        "tipo_marcacao_original": row.get("tipo_original"),
        "instante_solicitado": iso(row.get("instante_proposto")),
        "tipo_marcacao_solicitado": row.get("tipo_marcacao_proposto"),
        "criada_em": iso(row.get("created_at")),
        "analisada_em": iso(row.get("decided_at")),
        "observacao": row.get("decisao"),
        "funcionario": row.get("funcionario_nome"),
        "matricula": row.get("matricula"),
        "solicitante": row.get("solicitante_nome"),
        "analisador": row.get("analisador_nome"),
    }


def _audit(cursor, action, correction_id, metadata=None):
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id, ator_usuario_id, acao, entidade_tipo, entidade_id, metadados)
           VALUES (%s, %s, %s, 'correcao', %s, %s)""",
        (g.auth_context["empresa_id"], g.auth_context["user_id"], action, correction_id, psycopg2.extras.Json(metadata or {})),
    )


def _notify(cursor, user_id, title, message):
    cursor.execute(
        """INSERT INTO notificacoes (empresa_id, usuario_id, tipo, titulo, mensagem)
           VALUES (%s, %s, 'correcao', %s, %s)""",
        (g.auth_context["empresa_id"], user_id, title, message),
    )


DETAIL_SQL = """
    SELECT c.*, m.instante AS instante_original, m.tipo AS tipo_original,
           u.nome AS funcionario_nome, f.matricula,
           us.nome AS solicitante_nome, ua.nome AS analisador_nome
    FROM correcoes c
    INNER JOIN funcionarios f ON f.id = c.funcionario_id AND f.empresa_id = c.empresa_id
    INNER JOIN usuarios u ON u.id = f.usuario_id
    INNER JOIN usuarios us ON us.id = c.solicitante_usuario_id
    LEFT JOIN usuarios ua ON ua.id = c.responsavel_decisao_usuario_id
    LEFT JOIN marcacoes m ON m.id = c.marcacao_original_id
       AND m.empresa_id = c.empresa_id AND m.funcionario_id = c.funcionario_id
"""


@occurrences_bp.route("/ocorrencias")
@require_roles(*MANAGEMENT_ROLES)
def occurrences_page():
    return render_template("ocorrencias.html")


@occurrences_bp.post("/api/ocorrencias")
@access_token_required
def create_occurrence():
    connection = None
    try:
        category, operation, marking_id, reason, instant, marking_type = _validate_request(_payload())
        connection = conectar_bd()
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if marking_id:
            cursor.execute(
                """SELECT id FROM marcacoes WHERE id = %s AND empresa_id = %s
                   AND funcionario_id = %s AND estado = 'confirmada'""",
                (marking_id, g.auth_context["empresa_id"], g.auth_context["funcionario_id"]),
            )
            if not cursor.fetchone():
                connection.rollback()
                return jsonify({"erro": "Marcação não encontrada."}), 404
        cursor.execute(
            """INSERT INTO ocorrencias
               (empresa_id, funcionario_id, marcacao_id, tipo, descricao,
                estado, primeira_ocorrencia_at)
               VALUES (%s,%s,%s,'outra',%s,'aberta',clock_timestamp())
               RETURNING id""",
            (g.auth_context["empresa_id"], g.auth_context["funcionario_id"], marking_id, reason),
        )
        occurrence_id = cursor.fetchone()["id"]
        cursor.execute(
            """INSERT INTO correcoes
               (empresa_id, funcionario_id, ocorrencia_id, marcacao_original_id, solicitante_usuario_id,
                tipo, categoria, instante_proposto, tipo_marcacao_proposto, motivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (g.auth_context["empresa_id"], g.auth_context["funcionario_id"], occurrence_id, marking_id,
             g.auth_context["user_id"], operation, category, instant, marking_type, reason),
        )
        row = cursor.fetchone()
        _audit(cursor, "ocorrencia.criada", row["id"], {"categoria": category})
        connection.commit()
        return jsonify(_serialize(row)), 201
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        if connection:
            connection.rollback()
        return jsonify({"erro": "Não foi possível criar a ocorrência."}), 500
    finally:
        if connection:
            connection.close()


def _list_filters(management=False):
    allowed = {"status", "inicio", "fim", "tipo"} | ({"funcionario_id"} if management else set())
    if set(request.args) - allowed:
        raise ValueError("Filtro não permitido.")
    status = request.args.get("status")
    if status and status not in STATUS_TO_DB:
        raise ValueError("Status inválido.")
    category = request.args.get("tipo")
    if category and category not in {*CATEGORIES, "outro"}:
        raise ValueError("Tipo inválido.")
    employee = _uuid(request.args["funcionario_id"], "Funcionário") if management and request.args.get("funcionario_id") else None
    start, end = _date(request.args.get("inicio"), "Data inicial"), _date(request.args.get("fim"), "Data final")
    if start and end and end < start:
        raise ValueError("Data final não pode anteceder a inicial.")
    return employee, STATUS_TO_DB.get(status), category, *_utc_bounds(start, end)


def _list_rows(management=False):
    employee, status, category, start, end = _list_filters(management)
    conditions = ["c.empresa_id = %s"]
    params = [g.auth_context["empresa_id"]]
    if not management:
        conditions += ["c.funcionario_id = %s", "c.solicitante_usuario_id = %s"]
        params += [g.auth_context["funcionario_id"], g.auth_context["user_id"]]
    elif employee:
        conditions.append("c.funcionario_id = %s")
        params.append(employee)
    for clause, value in (("c.estado = %s", status), ("c.categoria = %s", category), ("c.created_at >= %s", start), ("c.created_at < %s", end)):
        if value is not None:
            conditions.append(clause); params.append(value)
    connection = conectar_bd()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(DETAIL_SQL + " WHERE " + " AND ".join(conditions) + " ORDER BY c.created_at DESC, c.id DESC", tuple(params))
        return [_serialize(row) for row in cursor.fetchall()]
    finally:
        cursor.close(); connection.close()


@occurrences_bp.get("/api/ocorrencias")
@access_token_required
def list_own_occurrences():
    try:
        return jsonify({"ocorrencias": _list_rows(False)})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar as ocorrências."}), 500


def _detail(correction_id, management):
    identifier = _uuid(correction_id, "Ocorrência")
    connection = conectar_bd(); cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["c.id = %s", "c.empresa_id = %s"]
        params = [identifier, g.auth_context["empresa_id"]]
        if not management:
            conditions += ["c.funcionario_id = %s", "c.solicitante_usuario_id = %s"]
            params += [g.auth_context["funcionario_id"], g.auth_context["user_id"]]
        cursor.execute(DETAIL_SQL + " WHERE " + " AND ".join(conditions), tuple(params))
        row = cursor.fetchone()
        return (_serialize(row), 200) if row else ({"erro": "Ocorrência não encontrada."}, 404)
    finally:
        cursor.close(); connection.close()


@occurrences_bp.get("/api/ocorrencias/<correction_id>")
@access_token_required
def own_occurrence_detail(correction_id):
    try:
        body, status = _detail(correction_id, False); return jsonify(body), status
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar a ocorrência."}), 500


@occurrences_bp.get("/api/gestao/ocorrencias")
@require_roles(*MANAGEMENT_ROLES)
def management_occurrences():
    try:
        return jsonify({"ocorrencias": _list_rows(True)})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar as ocorrências."}), 500


@occurrences_bp.get("/api/gestao/ocorrencias/<correction_id>")
@require_roles(*MANAGEMENT_ROLES)
def management_occurrence_detail(correction_id):
    try:
        body, status = _detail(correction_id, True); return jsonify(body), status
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar a ocorrência."}), 500


def _transition(correction_id, target, observation, own=False):
    connection = conectar_bd(); cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["id = %s", "empresa_id = %s"]
        params = [_uuid(correction_id, "Ocorrência"), g.auth_context["empresa_id"]]
        if own:
            conditions += ["funcionario_id = %s", "solicitante_usuario_id = %s"]
            params += [g.auth_context["funcionario_id"], g.auth_context["user_id"]]
        cursor.execute("SELECT * FROM correcoes WHERE " + " AND ".join(conditions) + " FOR UPDATE", tuple(params))
        row = cursor.fetchone()
        if not row:
            connection.rollback(); return {"erro": "Ocorrência não encontrada."}, 404
        if row["estado"] != PENDING_DB:
            connection.rollback(); return {"erro": "A ocorrência já foi decidida."}, 409
        valid_shape = {
            "inclusao": not row.get("marcacao_original_id") and row.get("instante_proposto") and row.get("tipo_marcacao_proposto"),
            "alteracao_instante": row.get("marcacao_original_id") and row.get("instante_proposto"),
            "alteracao_tipo": row.get("marcacao_original_id") and row.get("tipo_marcacao_proposto"),
            "justificativa": True,
        }.get(row.get("tipo"), False)
        if target == "aprovada" and not valid_shape:
            connection.rollback(); return {"erro": "A solicitação não possui dados válidos para aprovação."}, 409
        if target == "aprovada" and row.get("marcacao_original_id"):
            cursor.execute("SELECT id FROM marcacoes WHERE id=%s AND empresa_id=%s AND funcionario_id=%s AND estado='confirmada' FOR UPDATE", (row["marcacao_original_id"], g.auth_context["empresa_id"], row["funcionario_id"]))
            if not cursor.fetchone():
                connection.rollback(); return {"erro": "Marcação original não encontrada."}, 409
        if own:
            cursor.execute("UPDATE correcoes SET estado='cancelada', updated_at=clock_timestamp() WHERE id=%s RETURNING *", (row["id"],))
            updated = cursor.fetchone()
            if row.get("ocorrencia_id"):
                cursor.execute("UPDATE ocorrencias SET estado='arquivada', updated_at=clock_timestamp() WHERE id=%s", (row["ocorrencia_id"],))
            action, title, message = "ocorrencia.cancelada", None, None
        else:
            cursor.execute("""UPDATE correcoes SET estado=%s, responsavel_decisao_usuario_id=%s,
                decisao=%s, decided_at=clock_timestamp(), updated_at=clock_timestamp()
                WHERE id=%s RETURNING *""", (target, g.auth_context["user_id"], observation, row["id"]))
            updated = cursor.fetchone()
            if row.get("ocorrencia_id"):
                cursor.execute("""UPDATE ocorrencias SET estado='resolvida', responsavel_usuario_id=%s,
                    decisao=%s, resolved_at=clock_timestamp(), updated_at=clock_timestamp()
                    WHERE id=%s""", (g.auth_context["user_id"], target, row["ocorrencia_id"]))
            action = f"ocorrencia.{target}"
            title = "Correção de ponto aprovada" if target == "aprovada" else "Correção de ponto rejeitada"
            message = "Sua solicitação de correção de ponto foi aprovada." if target == "aprovada" else "Sua solicitação de correção de ponto foi rejeitada."
        _audit(cursor, action, row["id"], {"categoria": row["categoria"], "estado": target})
        if title:
            _notify(cursor, row["solicitante_usuario_id"], title, message)
        connection.commit()
        return _serialize(updated), 200
    except ValueError as exc:
        connection.rollback(); return {"erro": str(exc)}, 400
    except Exception as exc:
        connection.rollback()
        if getattr(exc, "pgcode", None) == "23505":
            return {"erro": "Já existe correção aprovada para esta marcação."}, 409
        return {"erro": "Não foi possível concluir a decisão."}, 500
    finally:
        cursor.close(); connection.close()


@occurrences_bp.post("/api/ocorrencias/<correction_id>/cancelar")
@access_token_required
def cancel_occurrence(correction_id):
    body, status = _transition(correction_id, "cancelada", None, True); return jsonify(body), status


def _decision_payload(require_observation=False):
    data = request.get_json(silent=True) or {}
    if set(data) - {"observacao"}:
        raise ValueError("Payload administrativo inválido.")
    observation = str(data.get("observacao") or "").strip()
    if require_observation and not observation:
        raise ValueError("Observação é obrigatória para rejeição.")
    return observation or None


@occurrences_bp.post("/api/gestao/ocorrencias/<correction_id>/aprovar")
@require_roles(*MANAGEMENT_ROLES)
def approve_occurrence(correction_id):
    try:
        observation = _decision_payload()
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    body, status = _transition(correction_id, "aprovada", observation); return jsonify(body), status


@occurrences_bp.post("/api/gestao/ocorrencias/<correction_id>/rejeitar")
@require_roles(*MANAGEMENT_ROLES)
def reject_occurrence(correction_id):
    try:
        observation = _decision_payload(True)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    body, status = _transition(correction_id, "rejeitada", observation); return jsonify(body), status
