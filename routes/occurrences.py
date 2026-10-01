"""Solicitações pessoais e análise auditável de correções de ponto."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg2.extras
from flask import Blueprint, g, jsonify, render_template, request

from db import conectar_bd
from services.correction_workflow import (
    CorrectionWorkflowError,
    FORWARDED_HR,
    PENDING_MANAGER,
    allowed_actions,
    normalize_justification,
    transition_correction,
)
from services.facial_failure_workflow import (
    FacialFailureWorkflowError,
    transition_facial_failure_occurrence,
)
from services.management_scope import employee_scope_clause
from utils.auth_decorator import access_token_required, require_roles

occurrences_bp = Blueprint("occurrences", __name__)
MANAGEMENT_ROLES = ("administrador", "gestor", "rh")
FACIAL_FAILURE_STATES = {"aberta", "em_analise", "resolvida", "descartada"}
CATEGORIES = {
    "esquecimento_marcacao": "inclusao",
    "horario_incorreto": "alteracao_instante",
    "tipo_incorreto": "alteracao_tipo",
    "justificativa": "justificativa",
}
CLOCK_TYPES = {"entrada", "saida_intervalo", "retorno_intervalo", "saida"}
MAX_REASON_LENGTH = 1000
PENDING_DB = PENDING_MANAGER
STATUS_TO_DB = {
    "pendente_gestor": PENDING_MANAGER,
    "encaminhada_rh": FORWARDED_HR,
    "aprovada": "aprovada",
    "rejeitada": "rejeitada",
    "cancelada": "cancelada",
}
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
    reason = " ".join(str(data.get("motivo") or "").split())
    if not reason:
        raise ValueError("Motivo é obrigatório.")
    if len(reason) > MAX_REASON_LENGTH:
        raise ValueError(f"Motivo deve ter no máximo {MAX_REASON_LENGTH} caracteres.")
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


def _serialize(row, management=False):
    def iso(value):
        return value.isoformat() if value else None

    serialized = {
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
    serialized["acoes_permitidas"] = allowed_actions(
        g.auth_context["perfil"], row["estado"], own=not management
    )
    return serialized


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


@occurrences_bp.route("/ocorrencias/falhas-faciais")
@require_roles(*MANAGEMENT_ROLES)
def facial_failure_occurrences_page():
    return render_template("falhasFaciais.html")


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
                 tipo, categoria, instante_proposto, tipo_marcacao_proposto, motivo, estado)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pendente_gestor') RETURNING *""",
            (g.auth_context["empresa_id"], g.auth_context["funcionario_id"], occurrence_id, marking_id,
             g.auth_context["user_id"], operation, category, instant, marking_type, reason),
        )
        row = cursor.fetchone()
        _audit(cursor, "correcao.criada", row["id"], {
            "categoria": category,
            "estado_anterior": None,
            "estado_novo": PENDING_MANAGER,
            "papel": g.auth_context["perfil"],
            "empresa_id": str(g.auth_context["empresa_id"]),
            "funcionario_id": str(g.auth_context["funcionario_id"]),
        })
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
    if management:
        scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
        conditions.append("(" + scope_clause + ")")
        params.extend(scope_params)
    for clause, value in (("c.estado = %s", status), ("c.categoria = %s", category), ("c.created_at >= %s", start), ("c.created_at < %s", end)):
        if value is not None:
            conditions.append(clause); params.append(value)
    connection = conectar_bd()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(DETAIL_SQL + " WHERE " + " AND ".join(conditions) + " ORDER BY c.created_at DESC, c.id DESC", tuple(params))
        return [_serialize(row, management=management) for row in cursor.fetchall()]
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
        else:
            scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
            conditions.append("(" + scope_clause + ")")
            params.extend(scope_params)
        cursor.execute(DETAIL_SQL + " WHERE " + " AND ".join(conditions), tuple(params))
        row = cursor.fetchone()
        if not row:
            return {"erro": "Ocorrência não encontrada."}, 404
        cursor.execute(
            """SELECT a.acao, a.ocorrido_at, a.metadados, u.nome AS responsavel
               FROM auditoria a
               LEFT JOIN usuarios u ON u.id = a.ator_usuario_id
               WHERE a.empresa_id = %s AND a.entidade_tipo = 'correcao'
                 AND a.entidade_id = %s
               ORDER BY a.ocorrido_at ASC, a.id ASC""",
            (g.auth_context["empresa_id"], row["id"]),
        )
        body = _serialize(row, management=management)
        body["historico"] = [
            {
                "acao": event["acao"],
                "ocorrida_em": event["ocorrido_at"].isoformat(),
                "responsavel": event.get("responsavel"),
                "papel": event.get("metadados", {}).get("papel"),
                "estado_anterior": event.get("metadados", {}).get("estado_anterior"),
                "estado_novo": event.get("metadados", {}).get("estado_novo"),
                "observacao": event.get("metadados", {}).get("justificativa"),
            }
            for event in cursor.fetchall()
        ]
        return body, 200
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


@occurrences_bp.get("/api/gestao/ocorrencias/falhas-faciais")
@require_roles(*MANAGEMENT_ROLES)
def management_facial_failure_occurrences():
    connection = None
    cursor = None
    try:
        allowed = {"estado", "busca", "unidade_id", "equipe_id", "inicio", "fim"}
        if set(request.args) - allowed:
            raise ValueError("Filtro não permitido.")
        state = str(request.args.get("estado") or "").strip() or None
        if state and state not in FACIAL_FAILURE_STATES:
            raise ValueError("Estado inválido.")
        search = str(request.args.get("busca") or "").strip() or None
        if search and len(search) > 100:
            raise ValueError("Busca inválida.")
        unit_id = _uuid(request.args["unidade_id"], "Unidade") if request.args.get("unidade_id") else None
        team_id = _uuid(request.args["equipe_id"], "Equipe") if request.args.get("equipe_id") else None
        start = _date(request.args.get("inicio"), "Data inicial")
        end = _date(request.args.get("fim"), "Data final")
        if start and end and end < start:
            raise ValueError("Data final não pode anteceder a inicial.")
        start_utc, end_utc = _utc_bounds(start, end)

        conditions = [
            "o.empresa_id = %s",
            "o.tipo = 'falha_facial'",
            "o.ciclo_falha_facial_id IS NOT NULL",
        ]
        params = [g.auth_context["empresa_id"]]
        scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
        conditions.append("(" + scope_clause + ")")
        params.extend(scope_params)
        for clause, value in (
            ("o.estado = %s", state),
            ("f.unidade_id = %s", unit_id),
            ("f.equipe_id = %s", team_id),
            ("o.primeira_ocorrencia_at >= %s", start_utc),
            ("o.primeira_ocorrencia_at < %s", end_utc),
        ):
            if value is not None:
                conditions.append(clause)
                params.append(value)
        if search:
            conditions.append("(u.nome ILIKE %s OR f.matricula ILIKE %s)")
            params.extend((f"%{search}%", f"%{search}%"))

        connection = conectar_bd()
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """SELECT o.id, o.funcionario_id, o.primeira_ocorrencia_at, o.estado,
                      o.descricao, o.created_at, u.nome AS funcionario,
                      f.matricula, f.unidade_id, un.nome AS unidade,
                      f.equipe_id, eq.nome AS equipe
               FROM ocorrencias o
               INNER JOIN funcionarios f
                 ON f.id = o.funcionario_id AND f.empresa_id = o.empresa_id
               INNER JOIN usuarios u ON u.id = f.usuario_id
               INNER JOIN unidades un
                 ON un.id = f.unidade_id AND un.empresa_id = f.empresa_id
               LEFT JOIN equipes eq
                 ON eq.id = f.equipe_id AND eq.empresa_id = f.empresa_id
                AND eq.unidade_id = f.unidade_id
               WHERE """ + " AND ".join(conditions) + """
               ORDER BY o.primeira_ocorrencia_at DESC, o.id DESC""",
            tuple(params),
        )
        return jsonify({"ocorrencias": [
            {
                "id": str(row["id"]),
                "funcionario_id": str(row["funcionario_id"]),
                "funcionario": row["funcionario"],
                "matricula": row["matricula"],
                "unidade_id": str(row["unidade_id"]),
                "unidade": row["unidade"],
                "equipe_id": str(row["equipe_id"]) if row["equipe_id"] else None,
                "equipe": row["equipe"],
                "primeira_ocorrencia_at": row["primeira_ocorrencia_at"].isoformat(),
                "estado": row["estado"],
                "descricao": row["descricao"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in cursor.fetchall()
        ]})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar as ocorrências."}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@occurrences_bp.get("/api/gestao/ocorrencias/falhas-faciais/<occurrence_id>")
@require_roles(*MANAGEMENT_ROLES)
def management_facial_failure_occurrence_detail(occurrence_id):
    connection = None
    cursor = None
    try:
        identifier = _uuid(occurrence_id, "Ocorrência")
        connection = conectar_bd()
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
        cursor.execute(
            """SELECT o.id, o.funcionario_id, o.primeira_ocorrencia_at, o.estado,
                      o.descricao, o.created_at, o.resolved_at, o.decisao,
                      u.nome AS funcionario, f.matricula,
                      un.nome AS unidade, eq.nome AS equipe,
                      responsavel.nome AS responsavel
               FROM ocorrencias o
               INNER JOIN funcionarios f
                 ON f.id = o.funcionario_id AND f.empresa_id = o.empresa_id
               INNER JOIN usuarios u ON u.id = f.usuario_id
               INNER JOIN unidades un
                 ON un.id = f.unidade_id AND un.empresa_id = f.empresa_id
               LEFT JOIN equipes eq
                 ON eq.id = f.equipe_id AND eq.empresa_id = f.empresa_id
                AND eq.unidade_id = f.unidade_id
               LEFT JOIN usuarios responsavel ON responsavel.id = o.responsavel_usuario_id
               WHERE o.id = %s AND o.empresa_id = %s
                 AND o.tipo = 'falha_facial'
                 AND o.ciclo_falha_facial_id IS NOT NULL
                 AND (""" + scope_clause + """)""",
            (identifier, g.auth_context["empresa_id"], *scope_params),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"erro": "Ocorrência não encontrada."}), 404
        cursor.execute(
            """SELECT a.acao, a.ocorrido_at, a.metadados, ator.nome AS ator
               FROM auditoria a
               LEFT JOIN usuarios ator ON ator.id = a.ator_usuario_id
               WHERE a.empresa_id = %s AND a.entidade_tipo = 'ocorrencia'
                 AND a.entidade_id = %s
               ORDER BY a.ocorrido_at ASC, a.id ASC""",
            (g.auth_context["empresa_id"], identifier),
        )
        audit = cursor.fetchall()
        return jsonify({
            "id": str(row["id"]), "funcionario_id": str(row["funcionario_id"]),
            "funcionario": row["funcionario"], "matricula": row["matricula"],
            "unidade": row["unidade"], "equipe": row["equipe"],
            "primeira_ocorrencia_at": row["primeira_ocorrencia_at"].isoformat(),
            "estado": row["estado"], "descricao": row["descricao"],
            "created_at": row["created_at"].isoformat(),
            "origem": "automatica_falha_facial",
            "responsavel": row["responsavel"], "decisao": row["decisao"],
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "auditoria": [
                {
                    "acao": item["acao"],
                    "ocorrido_at": item["ocorrido_at"].isoformat(),
                    "ator": item["ator"],
                    "estado_anterior": (item.get("metadados") or {}).get("estado_anterior"),
                    "estado_novo": (item.get("metadados") or {}).get("estado_novo"),
                    "justificativa": (item.get("metadados") or {}).get("justificativa"),
                }
                for item in audit
            ],
        })
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar a ocorrência."}), 500
    finally:
        if cursor: cursor.close()
        if connection: connection.close()


def _facial_failure_transition_payload(require_justification=False):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict) or set(data) - {"justificativa"}:
        raise ValueError("Payload administrativo inválido.")
    justification = str(data.get("justificativa") or "").strip()
    if require_justification and not justification:
        raise ValueError("Justificativa é obrigatória para concluir a ocorrência.")
    return justification or None


def _facial_failure_transition_response(occurrence_id, target, require_justification=False):
    try:
        justification = _facial_failure_transition_payload(require_justification)
        row = transition_facial_failure_occurrence(
            g.auth_context, occurrence_id, target, justification
        )
        return jsonify({
            "id": str(row["id"]),
            "estado": row["estado"],
            "responsavel_usuario_id": str(row["responsavel_usuario_id"]),
            "decisao": row["decisao"],
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "updated_at": row["updated_at"].isoformat(),
        }), 200
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except FacialFailureWorkflowError as exc:
        return jsonify({"erro": exc.message}), exc.status_code
    except Exception:
        return jsonify({"erro": "Não foi possível atualizar a ocorrência."}), 500


@occurrences_bp.post("/api/gestao/ocorrencias/falhas-faciais/<occurrence_id>/iniciar-analise")
@require_roles(*MANAGEMENT_ROLES)
def start_facial_failure_occurrence_review(occurrence_id):
    return _facial_failure_transition_response(occurrence_id, "em_analise")


@occurrences_bp.post("/api/gestao/ocorrencias/falhas-faciais/<occurrence_id>/resolver")
@require_roles(*MANAGEMENT_ROLES)
def resolve_facial_failure_occurrence(occurrence_id):
    return _facial_failure_transition_response(occurrence_id, "resolvida", True)


@occurrences_bp.post("/api/gestao/ocorrencias/falhas-faciais/<occurrence_id>/descartar")
@require_roles(*MANAGEMENT_ROLES)
def discard_facial_failure_occurrence(occurrence_id):
    return _facial_failure_transition_response(occurrence_id, "descartada", True)


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
    try:
        identifier = _uuid(correction_id, "Ocorrência")
        updated = transition_correction(
            conectar_bd,
            g.auth_context,
            identifier,
            target,
            observation,
            own=own,
        )
        return _serialize(updated, management=not own), 200
    except ValueError as exc:
        return {"erro": str(exc)}, 400
    except CorrectionWorkflowError as exc:
        return {"erro": exc.message}, exc.status
    except Exception:
        return {"erro": "Não foi possível concluir a decisão."}, 500


@occurrences_bp.post("/api/ocorrencias/<correction_id>/cancelar")
@access_token_required
def cancel_occurrence(correction_id):
    body, status = _transition(correction_id, "cancelada", None, True); return jsonify(body), status


def _decision_payload(require_observation=False):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ValueError("JSON administrativo inválido.")
    if set(data) - {"observacao"}:
        raise ValueError("Payload administrativo inválido.")
    try:
        return normalize_justification(data.get("observacao"), require_observation)
    except CorrectionWorkflowError as exc:
        raise ValueError(exc.message) from exc


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


@occurrences_bp.post("/api/gestao/ocorrencias/<correction_id>/encaminhar-rh")
@require_roles(*MANAGEMENT_ROLES)
def forward_occurrence_to_hr(correction_id):
    try:
        observation = _decision_payload(True)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    body, status = _transition(correction_id, FORWARDED_HR, observation)
    return jsonify(body), status
