"""Consultas, espelho e exportações de ponto para gestão e titular.

Marcações vêm da visão efetiva; jornadas vêm exclusivamente dos snapshots
imutáveis. Os instantes permanecem ``timestamptz`` e nenhuma consulta
materializa ou altera estado.
"""

from collections import defaultdict
import csv
from datetime import date, datetime, time, timedelta, timezone
import io
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg2.extras
from docx import Document
from flask import Blueprint, g, jsonify, request, send_file
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from db import conectar_bd
from services.effective_timekeeping import fetch_effective_events
from services.management_scope import employee_scope_clause
from services.timekeeping_reports import (
    load_employee_report,
    operational_utc_bounds,
    summarize_mirror,
)
from utils.auth_decorator import require_roles

timekeeping_bp = Blueprint("timekeeping", __name__)
MANAGEMENT_ROLES = ("administrador", "gestor", "rh")
LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
CLOCK_TYPES = ("entrada", "saida_intervalo", "retorno_intervalo", "saida")
MAX_MIRROR_DAYS = 366
MAX_CONSOLIDATED_DAYS = 92
MAX_EXPORT_ROWS = 10000
MAX_CONSOLIDATED_EMPLOYEES = 100


def _parse_uuid(value, field_name):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} inválido.") from exc


def _parse_date(value, field_name):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} inválida.") from exc


def _parse_filters(args):
    if args.get("empresa_id") not in (None, ""):
        raise ValueError("A consulta não aceita empresa informada pelo cliente.")
    employee_id = _parse_uuid(args.get("funcionario_id"), "Funcionário")
    start_date = _parse_date(args.get("inicio"), "Data inicial")
    end_date = _parse_date(args.get("fim"), "Data final")
    if start_date and end_date and end_date < start_date:
        raise ValueError("A data final não pode anteceder a inicial.")
    if start_date and end_date and (end_date - start_date).days + 1 > MAX_MIRROR_DAYS:
        raise ValueError(f"O período máximo é de {MAX_MIRROR_DAYS} dias.")
    return employee_id, start_date, end_date


def _parse_required_period(args, *, maximum=MAX_MIRROR_DAYS):
    start_date = _parse_date(args.get("inicio"), "Data inicial")
    end_date = _parse_date(args.get("fim"), "Data final")
    if not start_date or not end_date:
        raise ValueError("Informe data inicial e data final.")
    if end_date < start_date:
        raise ValueError("A data final não pode anteceder a inicial.")
    if (end_date - start_date).days + 1 > maximum:
        raise ValueError(f"O período máximo é de {maximum} dias.")
    return start_date, end_date


def _utc_bounds(start_date, end_date):
    """Converte datas civis de São Paulo em limites UTC indexáveis."""
    start = None
    end_exclusive = None
    if start_date:
        start = datetime.combine(start_date, time.min, LOCAL_TIMEZONE).astimezone(
            timezone.utc
        )
    if end_date:
        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), time.min, LOCAL_TIMEZONE
        ).astimezone(timezone.utc)
    return start, end_exclusive


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

    saida_intervalo = events.get("saida_intervalo")
    retorno_intervalo = events.get("retorno_intervalo")
    if bool(saida_intervalo) != bool(retorno_intervalo):
        return "--"

    total_seconds = (saida - entrada).total_seconds()
    if saida_intervalo and retorno_intervalo:
        if not (entrada <= saida_intervalo <= retorno_intervalo <= saida):
            return "--"
        total_seconds -= (retorno_intervalo - saida_intervalo).total_seconds()
    return _format_duration(total_seconds)


def _aware_instant(value):
    # psycopg2 retorna timestamptz consciente de fuso. Este fallback deixa
    # mocks ingênuos explicitamente UTC, sem usar o relógio do dispositivo.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _serialize_daily_records(rows):
    grouped = defaultdict(dict)
    weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    ordered_rows = sorted(
        rows,
        key=lambda item: (_aware_instant(item["instante"]), str(item.get("id", ""))),
    )
    for row in ordered_rows:
        if row["tipo"] not in CLOCK_TYPES:
            continue
        try:
            presentation_zone = ZoneInfo(
                row.get("jornada_timezone") or "America/Sao_Paulo"
            )
        except Exception:
            presentation_zone = LOCAL_TIMEZONE
        local_instant = _aware_instant(row["instante"]).astimezone(presentation_zone)
        operational_date = row.get("data_operacional")
        if operational_date and not isinstance(operational_date, date):
            operational_date = date.fromisoformat(str(operational_date))
        local_date = operational_date or local_instant.date()
        # Duplicatas: primeira marcação efetiva de cada tipo na data operacional.
        # Nenhum registro histórico é apagado ou alterado.
        grouped[local_date].setdefault(
            row["tipo"],
            {
                "instante": local_instant,
                "ajustada": bool(row.get("ajustada")),
                "origem": (
                    "inclusao_aprovada"
                    if row.get("marcacao_original_id") is None and row.get("ajustada")
                    else ("correcao_aprovada" if row.get("ajustada") else "original")
                ),
            },
        )

    result = []
    for local_date in sorted(grouped):
        events = grouped[local_date]
        event_instants = {
            event_type: events[event_type]["instante"]
            for event_type in CLOCK_TYPES
            if events.get(event_type)
        }
        formatted = {
            event_type: (
                events[event_type]["instante"].strftime("%H:%M")
                if events.get(event_type)
                else "--:--"
            )
            for event_type in CLOCK_TYPES
        }
        result.append(
            {
                "data": local_date.isoformat(),
                "dia": weekdays[local_date.weekday()],
                "entrada": formatted["entrada"],
                "saida_intervalo": formatted["saida_intervalo"],
                "retorno_intervalo": formatted["retorno_intervalo"],
                "volta_intervalo": formatted["retorno_intervalo"],
                "saida": formatted["saida"],
                "total": _daily_total(event_instants),
                "ajustada": any(item["ajustada"] for item in events.values()),
                "ajustes": [
                    event_type
                    for event_type in CLOCK_TYPES
                    if events.get(event_type) and events[event_type]["ajustada"]
                ],
                "data_operacional": local_date.isoformat(),
                "timezone": next(
                    (item["instante"].tzinfo.key for item in events.values()
                     if getattr(item["instante"].tzinfo, "key", None)),
                    "America/Sao_Paulo",
                ),
                "origens": {
                    event_type: events[event_type]["origem"]
                    for event_type in CLOCK_TYPES
                    if events.get(event_type)
                },
            }
        )
    return result


def _fetch_employee_records(cursor, auth_context, employee_id, start_date, end_date):
    scope_clause, scope_params = employee_scope_clause(auth_context, "f")
    cursor.execute(
        """
        SELECT f.id AS funcionario_id, u.nome, f.matricula
        FROM funcionarios f
        INNER JOIN usuarios u ON u.id = f.usuario_id
        WHERE f.id = %s AND f.empresa_id = %s
        AND (""" + scope_clause + ")",
        (employee_id, auth_context["empresa_id"], *scope_params),
    )
    employee = cursor.fetchone()
    if not employee:
        return None, []

    if start_date and end_date:
        start_utc, end_utc_exclusive = operational_utc_bounds(start_date, end_date)
    else:
        start_utc, end_utc_exclusive = _utc_bounds(start_date, end_date)
    rows = fetch_effective_events(
        cursor, auth_context["empresa_id"], employee_id, start_utc, end_utc_exclusive
    )
    return employee, _serialize_daily_records(rows)


def _load_management_records(auth_context, employee_id, start_date, end_date):
    connection = conectar_bd()
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        return _fetch_employee_records(
            cursor, auth_context, employee_id, start_date, end_date
        )
    finally:
        cursor.close()
        connection.close()


def _load_mirror(auth_context, employee_id, start_date, end_date, *, personal=False):
    connection = conectar_bd()
    connection.set_session(readonly=True, autocommit=False)
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if personal:
            cursor.execute(
                """SELECT f.id AS funcionario_id,u.nome,f.matricula
                   FROM funcionarios f
                   INNER JOIN usuarios u ON u.id=f.usuario_id
                   WHERE f.id=%s AND f.empresa_id=%s""",
                (employee_id, auth_context["empresa_id"]),
            )
        else:
            scope_clause, scope_params = employee_scope_clause(auth_context, "f")
            cursor.execute(
                """SELECT f.id AS funcionario_id,u.nome,f.matricula
                   FROM funcionarios f
                   INNER JOIN usuarios u ON u.id=f.usuario_id
                   WHERE f.id=%s AND f.empresa_id=%s AND ("""
                + scope_clause
                + ")",
                (employee_id, auth_context["empresa_id"], *scope_params),
            )
        employee = cursor.fetchone()
        if not employee:
            return None, []
        return employee, load_employee_report(
            cursor,
            auth_context["empresa_id"],
            employee_id,
            start_date,
            end_date,
        )
    finally:
        connection.rollback()
        cursor.close()
        connection.close()


def _format_date_br(value):
    return date.fromisoformat(value).strftime("%d/%m/%Y")


def _spreadsheet_cell(value):
    """Neutraliza texto interpretável como fórmula por CSV/XLSX."""
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _tabular_values(item):
    return (
        item["dia"],
        _format_date_br(item["data"]),
        item["entrada"],
        item["saida_intervalo"],
        item["retorno_intervalo"],
        item["saida"],
        item["total"],
    )


def _export_csv(records):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        ["Dia", "Data", "Entrada", "Saída Int.", "Retorno Int.", "Saída", "Total"]
    )
    for item in records:
        writer.writerow([_spreadsheet_cell(value) for value in _tabular_values(item)])
    payload = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    payload.seek(0)
    return payload


def _draw_pdf_header(pdf, y):
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Relatório de Controle de Ponto")
    y -= 30
    pdf.setFont("Helvetica", 9)
    positions = (40, 95, 160, 220, 295, 370, 430)
    labels = ("Dia", "Data", "Entrada", "Saída Int.", "Retorno Int.", "Saída", "Total")
    for x, label in zip(positions, labels):
        pdf.drawString(x, y, label)
    y -= 15
    pdf.line(40, y, 550, y)
    return y


def _export_pdf(records):
    payload = io.BytesIO()
    pdf = canvas.Canvas(payload, pagesize=A4)
    _, page_height = A4
    y = _draw_pdf_header(pdf, page_height - 40)
    for item in records:
        y -= 18
        if y < 50:
            pdf.showPage()
            y = _draw_pdf_header(pdf, page_height - 40) - 18
        values = (
            item["dia"],
            _format_date_br(item["data"]),
            item["entrada"],
            item["saida_intervalo"],
            item["retorno_intervalo"],
            item["saida"],
            item["total"],
        )
        for x, value in zip((40, 95, 160, 220, 295, 370, 430), values):
            pdf.drawString(x, y, str(value))
    pdf.save()
    payload.seek(0)
    return payload


def _export_docx(records):
    document = Document()
    document.add_heading("Relatório de Controle de Ponto", level=1)
    table = document.add_table(rows=1, cols=7)
    table.style = "Table Grid"
    headers = ("Dia", "Data", "Entrada", "Saída Int.", "Retorno Int.", "Saída", "Total")
    for cell, label in zip(table.rows[0].cells, headers):
        cell.text = label
    for item in records:
        values = (
            item["dia"],
            _format_date_br(item["data"]),
            item["entrada"],
            item["saida_intervalo"],
            item["retorno_intervalo"],
            item["saida"],
            item["total"],
        )
        for cell, value in zip(table.add_row().cells, values):
            cell.text = str(value)
    payload = io.BytesIO()
    document.save(payload)
    payload.seek(0)
    return payload


def _export_xlsx(records):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Espelho de ponto")
    headers = ("Dia", "Data", "Entrada", "Saída Int.", "Retorno Int.", "Saída", "Total")
    sheet.append(headers)
    for item in records:
        sheet.append([_spreadsheet_cell(value) for value in _tabular_values(item)])
    payload = io.BytesIO()
    workbook.save(payload)
    payload.seek(0)
    return payload


MIRROR_HEADERS = (
    "Data operacional",
    "Entrada",
    "Saída Int.",
    "Retorno Int.",
    "Saída",
    "Duração descritiva",
    "Estado informativo",
    "Fuso",
)


def _mirror_export_rows(mirror):
    rows = []
    for day in mirror:
        by_type = {
            event["tipo"]: event.get("efetiva")
            for event in day["eventos"]
            if event.get("efetiva")
        }
        rows.append(
            (
                _format_date_br(day["data_operacional"]),
                (by_type.get("entrada") or {}).get("horario", "--:--"),
                (by_type.get("saida_intervalo") or {}).get("horario", "--:--"),
                (by_type.get("retorno_intervalo") or {}).get("horario", "--:--"),
                (by_type.get("saida") or {}).get("horario", "--:--"),
                day.get("duracao_descritiva") or "--",
                day["estado_informativo"],
                day["timezone"],
            )
        )
    return rows


def _export_mirror_csv(mirror):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(MIRROR_HEADERS)
    for row in _mirror_export_rows(mirror):
        writer.writerow([_spreadsheet_cell(value) for value in row])
    payload = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    payload.seek(0)
    return payload


def _export_mirror_xlsx(mirror):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Espelho de ponto")
    sheet.append(MIRROR_HEADERS)
    for row in _mirror_export_rows(mirror):
        sheet.append([_spreadsheet_cell(value) for value in row])
    payload = io.BytesIO()
    workbook.save(payload)
    payload.seek(0)
    return payload


def _export_mirror_docx(mirror):
    document = Document()
    document.add_heading("Espelho de ponto — informativo", level=1)
    table = document.add_table(rows=1, cols=len(MIRROR_HEADERS))
    table.style = "Table Grid"
    for cell, label in zip(table.rows[0].cells, MIRROR_HEADERS):
        cell.text = label
    for row in _mirror_export_rows(mirror):
        for cell, value in zip(table.add_row().cells, row):
            cell.text = str(value)
    payload = io.BytesIO()
    document.save(payload)
    payload.seek(0)
    return payload


def _export_mirror_pdf(mirror):
    payload = io.BytesIO()
    page = landscape(A4)
    pdf = canvas.Canvas(payload, pagesize=page)
    _, height = page
    positions = (28, 110, 175, 240, 305, 370, 460, 650)

    def header():
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(28, height - 28, "Espelho de ponto - informativo")
        pdf.setFont("Helvetica", 7)
        for x, label in zip(positions, MIRROR_HEADERS):
            pdf.drawString(x, height - 48, label[:25])
        return height - 62

    y = header()
    for row in _mirror_export_rows(mirror):
        if y < 30:
            pdf.showPage()
            y = header()
        for x, value in zip(positions, row):
            pdf.drawString(x, y, str(value)[:28])
        y -= 15
    pdf.save()
    payload.seek(0)
    return payload


@timekeeping_bp.get("/api/gestao/funcionarios")
@require_roles(*MANAGEMENT_ROLES)
def funcionarios_gestao():
    connection = conectar_bd()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
        cursor.execute(
            """
            SELECT f.id AS funcionario_id, u.nome, f.matricula
            FROM funcionarios f
            INNER JOIN usuarios u ON u.id = f.usuario_id
            WHERE f.empresa_id = %s
              AND f.status = 'ativo'
              AND u.status = 'ativo'
              AND (""" + scope_clause + """)
            ORDER BY u.nome, f.id
            """,
            (g.auth_context["empresa_id"], *scope_params),
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
    except Exception:
        return jsonify({"erro": "Não foi possível carregar os funcionários."}), 500
    finally:
        cursor.close()
        connection.close()


@timekeeping_bp.get("/api/gestao/pontos")
@require_roles(*MANAGEMENT_ROLES)
def pontos_gestao():
    try:
        employee_id, start_date, end_date = _parse_filters(request.args)
        employee, records = _load_management_records(
            g.auth_context, employee_id, start_date, end_date
        )
        if not employee:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        return jsonify(records)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível consultar as marcações."}), 500


def _mirror_payload(employee, mirror, start_date, end_date):
    return {
        "funcionario": {
            "id": str(employee["funcionario_id"]),
            "nome": employee["nome"],
            "matricula": employee["matricula"],
        },
        "periodo": {"inicio": start_date.isoformat(), "fim": end_date.isoformat()},
        "timezone_padrao": "America/Sao_Paulo",
        "dias": mirror,
        "resumo": summarize_mirror(mirror),
        "natureza": "informativa_nao_trabalhista",
    }


@timekeeping_bp.get("/api/gestao/espelho")
@require_roles(*MANAGEMENT_ROLES)
def espelho_gestao():
    try:
        if request.args.get("empresa_id") not in (None, ""):
            raise ValueError("A consulta não aceita empresa informada pelo cliente.")
        employee_id = _parse_uuid(request.args.get("funcionario_id"), "Funcionário")
        start_date, end_date = _parse_required_period(request.args)
        employee, mirror = _load_mirror(
            g.auth_context, employee_id, start_date, end_date
        )
        if not employee:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        return jsonify(_mirror_payload(employee, mirror, start_date, end_date))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível gerar o espelho de ponto."}), 500


@timekeeping_bp.get("/api/gestao/espelho/exportar")
@require_roles(*MANAGEMENT_ROLES)
def exportar_espelho_gestao():
    try:
        export_format = str(request.args.get("formato") or "").lower()
        if export_format not in {"csv", "pdf", "xlsx", "word", "doc", "docx"}:
            raise ValueError("Formato inválido.")
        if request.args.get("empresa_id") not in (None, ""):
            raise ValueError("A consulta não aceita empresa informada pelo cliente.")
        employee_id = _parse_uuid(request.args.get("funcionario_id"), "Funcionário")
        start_date, end_date = _parse_required_period(request.args)
        employee, mirror = _load_mirror(
            g.auth_context, employee_id, start_date, end_date
        )
        if not employee:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        if not mirror:
            return jsonify({"erro": "Nenhum registro encontrado para exportação."}), 404
        exporters = {
            "csv": (_export_mirror_csv, "espelho_ponto.csv", "text/csv"),
            "pdf": (_export_mirror_pdf, "espelho_ponto.pdf", "application/pdf"),
            "xlsx": (
                _export_mirror_xlsx,
                "espelho_ponto.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "word": (
                _export_mirror_docx,
                "espelho_ponto.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "doc": (
                _export_mirror_docx,
                "espelho_ponto.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "docx": (
                _export_mirror_docx,
                "espelho_ponto.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        }
        exporter, filename, mimetype = exporters[export_format]
        response = send_file(
            exporter(mirror),
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype,
            max_age=0,
        )
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível exportar o espelho de ponto."}), 500


@timekeeping_bp.get("/api/me/espelho")
@require_roles("funcionario")
def espelho_pessoal():
    try:
        if request.args.get("funcionario_id") not in (None, "") or request.args.get(
            "empresa_id"
        ) not in (None, ""):
            raise ValueError("A consulta pessoal não aceita identidade informada pelo cliente.")
        start_date, end_date = _parse_required_period(request.args)
        employee_id = g.auth_context.get("funcionario_id")
        if not employee_id:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        employee, mirror = _load_mirror(
            g.auth_context,
            str(employee_id),
            start_date,
            end_date,
            personal=True,
        )
        if not employee:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        return jsonify(_mirror_payload(employee, mirror, start_date, end_date))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível gerar o espelho de ponto."}), 500


def _parse_page(args):
    try:
        page = int(args.get("pagina", "1"))
        limit = int(args.get("limite", "50"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Paginação inválida.") from exc
    if page < 1 or not 1 <= limit <= MAX_CONSOLIDATED_EMPLOYEES:
        raise ValueError(
            f"Página deve ser positiva e limite deve ficar entre 1 e {MAX_CONSOLIDATED_EMPLOYEES}."
        )
    return page, limit


@timekeeping_bp.get("/api/gestao/relatorios/consolidado")
@require_roles(*MANAGEMENT_ROLES)
def relatorio_consolidado():
    connection = None
    cursor = None
    try:
        if request.args.get("empresa_id") not in (None, ""):
            raise ValueError("A consulta não aceita empresa informada pelo cliente.")
        start_date, end_date = _parse_required_period(
            request.args, maximum=MAX_CONSOLIDATED_DAYS
        )
        page, limit = _parse_page(request.args)
        employee_filter = request.args.get("funcionario_id")
        employee_filter = (
            _parse_uuid(employee_filter, "Funcionário") if employee_filter else None
        )
        unit_filter = request.args.get("unidade_id")
        unit_filter = _parse_uuid(unit_filter, "Unidade") if unit_filter else None
        team_filter = request.args.get("equipe_id")
        team_filter = _parse_uuid(team_filter, "Equipe") if team_filter else None
        scope_clause, scope_params = employee_scope_clause(g.auth_context, "f")
        connection = conectar_bd()
        connection.set_session(readonly=True, autocommit=False)
        cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """SELECT f.id AS funcionario_id,u.nome,f.matricula,
                      f.unidade_id,un.nome AS unidade,f.equipe_id,eq.nome AS equipe
               FROM funcionarios f
               INNER JOIN usuarios u ON u.id=f.usuario_id
               LEFT JOIN unidades un ON un.empresa_id=f.empresa_id AND un.id=f.unidade_id
               LEFT JOIN equipes eq ON eq.empresa_id=f.empresa_id AND eq.id=f.equipe_id
               WHERE f.empresa_id=%s AND (%s::uuid IS NULL OR f.id=%s)
                 AND (%s::uuid IS NULL OR f.unidade_id=%s)
                 AND (%s::uuid IS NULL OR f.equipe_id=%s)
                 AND ("""
            + scope_clause
            + ") ORDER BY u.nome,f.id LIMIT %s OFFSET %s",
            (
                g.auth_context["empresa_id"],
                employee_filter,
                employee_filter,
                unit_filter,
                unit_filter,
                team_filter,
                team_filter,
                *scope_params,
                limit + 1,
                (page - 1) * limit,
            ),
        )
        employees = cursor.fetchall()
        if employee_filter and not employees:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        has_more = len(employees) > limit
        employees = employees[:limit]
        employee_ids = [str(item["funcionario_id"]) for item in employees]
        occurrence_counts = defaultdict(lambda: defaultdict(int))
        if employee_ids:
            cursor.execute(
                """SELECT funcionario_id,tipo,estado,count(*) AS total
                   FROM ocorrencias
                   WHERE empresa_id=%s AND funcionario_id=ANY(%s::uuid[])
                     AND (primeira_ocorrencia_at AT TIME ZONE 'America/Sao_Paulo')::date
                         BETWEEN %s AND %s
                   GROUP BY funcionario_id,tipo,estado
                   ORDER BY funcionario_id,tipo,estado""",
                (g.auth_context["empresa_id"], employee_ids, start_date, end_date),
            )
            for row in cursor.fetchall():
                key = f"{row['tipo']}:{row['estado']}"
                occurrence_counts[str(row["funcionario_id"])][key] = int(row["total"])
        items = []
        for employee in employees:
            mirror = load_employee_report(
                cursor,
                g.auth_context["empresa_id"],
                str(employee["funcionario_id"]),
                start_date,
                end_date,
            )
            items.append(
                {
                    "funcionario": {
                        "id": str(employee["funcionario_id"]),
                        "nome": employee["nome"],
                        "matricula": employee["matricula"],
                        "unidade": employee.get("unidade"),
                        "equipe": employee.get("equipe"),
                    },
                    "indicadores": summarize_mirror(mirror),
                    "ocorrencias_por_tipo_estado": dict(
                        occurrence_counts[str(employee["funcionario_id"])]
                    ),
                }
            )
        return jsonify(
            {
                "periodo": {
                    "inicio": start_date.isoformat(),
                    "fim": end_date.isoformat(),
                },
                "pagina": page,
                "limite": limit,
                "tem_mais": has_more,
                "itens": items,
                "regra": {
                    "indicadores": "fatuais_e_informativos",
                    "tolerancia_cinco_minutos": "pendente_confirmacao_rh",
                    "efeito_trabalhista": "nao_calculado",
                },
            }
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível gerar o relatório consolidado."}), 500
    finally:
        if connection:
            connection.rollback()
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@timekeeping_bp.get("/api/gestao/marcacoes/<marking_id>/localizacao")
@require_roles("administrador", "rh")
def localizacao_marcacao(marking_id):
    try:
        identifier = _parse_uuid(marking_id, "Marcação")
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT m.id,m.unidade_id,m.latitude,m.longitude,
                          m.precisao_metros,m.distancia_unidade_metros,
                          m.localizacao_capturada_at,m.endereco_localizacao,
                          un.nome AS unidade
                   FROM marcacoes m
                   LEFT JOIN unidades un
                     ON un.id=m.unidade_id AND un.empresa_id=m.empresa_id
                   WHERE m.id=%s AND m.empresa_id=%s AND m.canal='mobile'""",
                (identifier, g.auth_context["empresa_id"]),
            )
            item = cursor.fetchone()
        if not item:
            return jsonify({"erro": "Marcação não encontrada."}), 404
        return jsonify({
            "id": str(item["id"]),
            "unidade_id": str(item["unidade_id"]),
            "unidade": item["unidade"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "precisao_metros": item["precisao_metros"],
            "distancia_unidade_metros": item["distancia_unidade_metros"],
            "capturada_em": item["localizacao_capturada_at"].isoformat(),
            "endereco": item["endereco_localizacao"],
        }), 200
    finally:
        connection.close()


@timekeeping_bp.get("/exportar-pontos")
@require_roles(*MANAGEMENT_ROLES)
def exportar_pontos_gestao():
    try:
        export_format = str(request.args.get("formato") or "").lower()
        if export_format not in {"csv", "pdf", "xlsx", "word", "doc", "docx"}:
            return jsonify({"erro": "Formato inválido."}), 400
        employee_id, start_date, end_date = _parse_filters(request.args)
        employee, records = _load_management_records(
            g.auth_context, employee_id, start_date, end_date
        )
        if not employee:
            return jsonify({"erro": "Funcionário não encontrado."}), 404
        if not records:
            return jsonify({"erro": "Nenhum registro encontrado para exportação."}), 404
        if len(records) > MAX_EXPORT_ROWS:
            return jsonify({"erro": "O relatório excede o limite de linhas."}), 413

        if export_format == "csv":
            return send_file(
                _export_csv(records),
                as_attachment=True,
                download_name="controle_ponto.csv",
                mimetype="text/csv",
            )
        if export_format == "pdf":
            return send_file(
                _export_pdf(records),
                as_attachment=True,
                download_name="controle_ponto.pdf",
                mimetype="application/pdf",
            )
        if export_format == "xlsx":
            return send_file(
                _export_xlsx(records),
                as_attachment=True,
                download_name="controle_ponto.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return send_file(
            _export_docx(records),
            as_attachment=True,
            download_name="controle_ponto.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        return jsonify({"erro": "Não foi possível exportar as marcações."}), 500
