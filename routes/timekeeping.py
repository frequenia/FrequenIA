from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg2.extras
from flask import Blueprint, g, jsonify, request

from db import conectar_bd
from utils.auth_decorator import require_roles


timekeeping_bp = Blueprint("timekeeping", __name__)
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
LOCAL_TIMEZONE_NAME = "America/Sao_Paulo"


def _parse_date(value, field_name):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} inválida.") from exc


def _format_duration(seconds):
    if seconds is None or seconds < 0:
        return "--"
    total_minutes = int(seconds // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h{minutes:02d}"


def _daily_total(events):
    entrada = events.get("entrada")
    saida = events.get("saida")
    if not entrada or not saida or saida < entrada:
        return "--"

    total_seconds = (saida - entrada).total_seconds()
    saida_intervalo = events.get("saida_intervalo")
    retorno_intervalo = events.get("retorno_intervalo")
    if (
        saida_intervalo
        and retorno_intervalo
        and retorno_intervalo >= saida_intervalo
    ):
        total_seconds -= (retorno_intervalo - saida_intervalo).total_seconds()

    return _format_duration(total_seconds)


def _serialize_daily_records(rows):
    grouped = defaultdict(dict)
    weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

    for row in rows:
        local_instant = row["instante"].astimezone(LOCAL_TIMEZONE)
        local_date = local_instant.date()
        # Mantém a primeira marcação confirmada de cada tipo no dia.
        grouped[local_date].setdefault(row["tipo"], local_instant)

    result = []
    for local_date in sorted(grouped):
        events = grouped[local_date]
        result.append(
            {
                "data": local_date.isoformat(),
                "dia": weekdays[local_date.weekday()],
                "entrada": events.get("entrada").strftime("%H:%M") if events.get("entrada") else "--:--",
                "saida_intervalo": events.get("saida_intervalo").strftime("%H:%M") if events.get("saida_intervalo") else "--:--",
                "volta_intervalo": events.get("retorno_intervalo").strftime("%H:%M") if events.get("retorno_intervalo") else "--:--",
                "saida": events.get("saida").strftime("%H:%M") if events.get("saida") else "--:--",
                "total": _daily_total(events),
            }
        )
    return result


@timekeeping_bp.get("/api/gestao/funcionarios")
@require_roles("administrador", "gestor", "rh")
def funcionarios_gestao():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT f.id AS funcionario_id, u.nome, f.matricula
            FROM funcionarios f
            INNER JOIN usuarios u ON u.id = f.usuario_id
            WHERE f.empresa_id = %s
              AND f.status = 'ativo'
              AND u.status = 'ativo'
            ORDER BY u.nome, f.id
            """,
            (g.auth_context["empresa_id"],),
        )
        return jsonify(
            [
                {
                    "funcionario_id": str(item["funcionario_id"]),
                    "nome": item["nome"],
                    "matricula": item["matricula"],
                }
                for item in cursor.fetchall()
            ]
        )
    finally:
        cursor.close()
        conn.close()


@timekeeping_bp.get("/api/gestao/pontos")
@require_roles("administrador", "gestor", "rh")
def pontos_gestao():
    try:
        funcionario_id = request.args.get("funcionario_id")
        if not funcionario_id:
            return jsonify({"erro": "Funcionário é obrigatório."}), 400

        data_inicio = _parse_date(request.args.get("inicio"), "Data inicial")
        data_fim = _parse_date(request.args.get("fim"), "Data final")
        if data_inicio and data_fim and data_fim < data_inicio:
            return jsonify({"erro": "A data final não pode anteceder a inicial."}), 400

        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute(
                """
                SELECT 1
                FROM funcionarios
                WHERE id = %s AND empresa_id = %s
                """,
                (funcionario_id, g.auth_context["empresa_id"]),
            )
            if not cursor.fetchone():
                return jsonify({"erro": "Funcionário não encontrado."}), 404

            query = """
                SELECT tipo, instante
                FROM marcacoes
                WHERE empresa_id = %s
                  AND funcionario_id = %s
                  AND estado = 'confirmada'
            """
            params = [g.auth_context["empresa_id"], funcionario_id]

            if data_inicio:
                query += f" AND (instante AT TIME ZONE '{LOCAL_TIMEZONE_NAME}')::date >= %s"
                params.append(data_inicio)
            if data_fim:
                query += f" AND (instante AT TIME ZONE '{LOCAL_TIMEZONE_NAME}')::date <= %s"
                params.append(data_fim)

            query += " ORDER BY instante ASC, id ASC"
            cursor.execute(query, tuple(params))
            return jsonify(_serialize_daily_records(cursor.fetchall()))
        finally:
            cursor.close()
            conn.close()
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar as marcações."}), 500
