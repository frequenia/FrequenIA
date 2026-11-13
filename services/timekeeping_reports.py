"""Espelho e indicadores de ponto derivados de snapshots e visão efetiva.

Este módulo é somente leitura. Ele não materializa jornadas, não altera
marcações e não transforma indicadores operacionais em decisões trabalhistas.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.effective_timekeeping import fetch_effective_events


CLOCK_TYPES = ("entrada", "saida_intervalo", "retorno_intervalo", "saida")
MATCH_WINDOW_HOURS = 12


def operational_utc_bounds(start_date, end_date, timezone_name="America/Sao_Paulo"):
    """Inclui a janela de uma jornada noturna sem mudar o filtro operacional."""
    zone = ZoneInfo(timezone_name)
    start = datetime.combine(start_date, time.min, zone) - timedelta(
        hours=MATCH_WINDOW_HOURS
    )
    end = datetime.combine(end_date + timedelta(days=1), time.min, zone) + timedelta(
        hours=MATCH_WINDOW_HOURS
    )
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def fetch_snapshot_events(cursor, company_id, employee_id, start_date, end_date):
    cursor.execute(
        """
        SELECT jd.id AS snapshot_id,jd.data_operacional,jd.timezone,jd.origem,
               jd.versao,je.id AS evento_id,je.ordem,je.tipo,
               je.instante_esperado,je.marcacao_id
        FROM jornadas_diarias jd
        LEFT JOIN jornada_eventos_esperados je
          ON je.empresa_id=jd.empresa_id AND je.jornada_id=jd.id
        WHERE jd.empresa_id=%s AND jd.funcionario_id=%s
          AND jd.data_operacional BETWEEN %s AND %s
        ORDER BY jd.data_operacional,je.ordem,je.id
        """,
        (company_id, employee_id, start_date, end_date),
    )
    return cursor.fetchall()


def fetch_report_corrections(cursor, company_id, employee_id, start_date, end_date):
    """Retorna somente metadados necessários ao espelho, sem motivo ou anexo."""
    cursor.execute(
        """
        SELECT c.id,c.tipo,c.categoria,c.estado,c.created_at,c.decided_at,
               COALESCE(jd.data_operacional,proposta.data_operacional,
                   (COALESCE(c.instante_proposto,m.instante,c.created_at)
                    AT TIME ZONE 'America/Sao_Paulo')::date) AS data_operacional
        FROM correcoes c
        LEFT JOIN marcacoes m
          ON m.empresa_id=c.empresa_id
         AND m.funcionario_id=c.funcionario_id
         AND m.id=c.marcacao_original_id
        LEFT JOIN jornada_eventos_esperados je
          ON je.empresa_id=m.empresa_id AND je.id=m.jornada_evento_id
        LEFT JOIN jornadas_diarias jd
          ON jd.empresa_id=je.empresa_id AND jd.id=je.jornada_id
        LEFT JOIN LATERAL (
            SELECT jornada.data_operacional
            FROM jornadas_diarias jornada
            INNER JOIN jornada_eventos_esperados esperado
              ON esperado.empresa_id=jornada.empresa_id
             AND esperado.jornada_id=jornada.id
            WHERE jornada.empresa_id=c.empresa_id
              AND jornada.funcionario_id=c.funcionario_id
              AND c.instante_proposto IS NOT NULL
              AND c.instante_proposto >= esperado.instante_esperado - interval '12 hours'
              AND c.instante_proposto <= esperado.instante_esperado + interval '12 hours'
            ORDER BY abs(extract(epoch from
                (c.instante_proposto-esperado.instante_esperado))),
                jornada.data_operacional,esperado.ordem
            LIMIT 1
        ) proposta ON TRUE
        WHERE c.empresa_id=%s AND c.funcionario_id=%s
          AND COALESCE(jd.data_operacional,proposta.data_operacional,
              (COALESCE(c.instante_proposto,m.instante,c.created_at)
               AT TIME ZONE 'America/Sao_Paulo')::date) BETWEEN %s AND %s
        ORDER BY data_operacional,c.created_at,c.id
        """,
        (company_id, employee_id, start_date, end_date),
    )
    return cursor.fetchall()


def load_employee_report(cursor, company_id, employee_id, start_date, end_date):
    snapshot_rows = fetch_snapshot_events(
        cursor, company_id, employee_id, start_date, end_date
    )
    start_utc, end_utc = operational_utc_bounds(start_date, end_date)
    effective = fetch_effective_events(
        cursor, company_id, employee_id, start_utc, end_utc
    )
    corrections = fetch_report_corrections(
        cursor, company_id, employee_id, start_date, end_date
    )
    return build_mirror(
        snapshot_rows, effective, corrections, start_date, end_date
    )


def _date_value(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _safe_zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def _effective_operational_date(item):
    explicit = _date_value(item.get("data_operacional"))
    if explicit:
        return explicit
    zone = _safe_zone(item.get("jornada_timezone"))
    return _aware(item["instante"]).astimezone(zone).date()


def _public_effective(item, zone):
    local = _aware(item["instante"]).astimezone(zone)
    if item.get("marcacao_original_id") is None:
        source = "inclusao_aprovada"
    elif item.get("ajustada"):
        source = "correcao_aprovada"
    else:
        source = "original"
    return {
        "tipo": item["tipo"],
        "instante": local.isoformat(),
        "horario": local.strftime("%H:%M"),
        "origem": source,
        "ajustada": bool(item.get("ajustada")),
    }


def _match_events(expected, effective, zone):
    unmatched = list(range(len(effective)))
    result = []
    for event in expected:
        match_index = None
        direct = event.get("marcacao_id")
        if direct:
            for index in unmatched:
                if str(effective[index].get("marcacao_original_id")) == str(direct):
                    match_index = index
                    break
        if match_index is None:
            for index in unmatched:
                if effective[index].get("tipo") == event.get("tipo"):
                    match_index = index
                    break
        matched = effective[match_index] if match_index is not None else None
        if match_index is not None:
            unmatched.remove(match_index)
        expected_at = _aware(event["instante_esperado"])
        delta = None
        indicator = "nao_registrado"
        public_effective = None
        if matched:
            delta = int((_aware(matched["instante"]) - expected_at).total_seconds() // 60)
            indicator = (
                "apos_horario"
                if delta > 0
                else ("antes_horario" if delta < 0 else "no_horario")
            )
            public_effective = _public_effective(matched, zone)
        result.append(
            {
                "ordem": int(event["ordem"]),
                "tipo": event["tipo"],
                "instante_esperado": expected_at.astimezone(zone).isoformat(),
                "horario_esperado": expected_at.astimezone(zone).strftime("%H:%M"),
                "efetiva": public_effective,
                "diferenca_minutos": delta,
                "indicador_tempo": indicator,
                "classificacao_trabalhista": "pendente_rh_juridico",
            }
        )
    extras = [_public_effective(effective[index], zone) for index in unmatched]
    return result, extras


def _state(origin, expected, matched_count, snapshot_present, effective_count):
    if not snapshot_present:
        return "snapshot_ausente" if effective_count else "sem_evidencia"
    if origin == "folga":
        return "folga_com_marcacao" if effective_count else "folga"
    if origin == "sem_jornada" or not expected:
        return "sem_jornada_com_marcacao" if effective_count else "sem_jornada"
    if matched_count == len(expected):
        return "completo"
    if matched_count:
        return "incompleto"
    return "sem_marcacao"


def _descriptive_duration(effective):
    first = {}
    for item in effective:
        first.setdefault(item.get("tipo"), _aware(item["instante"]))
    start = first.get("entrada")
    end = first.get("saida")
    if not start or not end or end < start:
        return None
    break_start = first.get("saida_intervalo")
    break_end = first.get("retorno_intervalo")
    if bool(break_start) != bool(break_end):
        return None
    seconds = (end - start).total_seconds()
    if break_start and break_end:
        if not start <= break_start <= break_end <= end:
            return None
        seconds -= (break_end - break_start).total_seconds()
    minutes = int(seconds // 60)
    return f"{minutes // 60}h{minutes % 60:02d}"


def _correction_public(item):
    return {
        "tipo": item["tipo"],
        "categoria": item.get("categoria"),
        "estado": item["estado"],
        "criada_em": _aware(item["created_at"]).isoformat(),
        "decidida_em": (
            _aware(item["decided_at"]).isoformat() if item.get("decided_at") else None
        ),
    }


def build_mirror(snapshot_rows, effective_rows, corrections, start_date, end_date):
    snapshots = {}
    for row in snapshot_rows:
        operational_date = _date_value(row["data_operacional"])
        snapshot = snapshots.setdefault(
            operational_date,
            {
                "id": row["snapshot_id"],
                "timezone": row["timezone"],
                "origem": row["origem"],
                "versao": row["versao"],
                "events": [],
            },
        )
        if row.get("evento_id"):
            snapshot["events"].append(row)

    effective_by_date = defaultdict(list)
    for row in sorted(
        effective_rows,
        key=lambda item: (_aware(item["instante"]), str(item.get("id", ""))),
    ):
        effective_by_date[_effective_operational_date(row)].append(row)

    corrections_by_date = defaultdict(list)
    for row in corrections:
        corrections_by_date[_date_value(row["data_operacional"])].append(row)

    dates = set(snapshots) | set(effective_by_date) | set(corrections_by_date)
    current = start_date
    while current <= end_date:
        dates.add(current)
        current += timedelta(days=1)

    result = []
    for operational_date in sorted(dates):
        if operational_date < start_date or operational_date > end_date:
            continue
        snapshot = snapshots.get(operational_date)
        timezone_name = snapshot["timezone"] if snapshot else "America/Sao_Paulo"
        zone = _safe_zone(timezone_name)
        expected = snapshot["events"] if snapshot else []
        effective = effective_by_date.get(operational_date, [])
        matched, extras = _match_events(expected, effective, zone)
        matched_count = sum(1 for item in matched if item["efetiva"])
        result.append(
            {
                "data_operacional": operational_date.isoformat(),
                "timezone": timezone_name,
                "snapshot_presente": snapshot is not None,
                "snapshot_versao": snapshot["versao"] if snapshot else None,
                "origem_jornada": snapshot["origem"] if snapshot else None,
                "estado_informativo": _state(
                    snapshot["origem"] if snapshot else None,
                    expected,
                    matched_count,
                    snapshot is not None,
                    len(effective),
                ),
                "eventos": matched,
                "marcacoes_sem_evento": extras,
                "duracao_descritiva": _descriptive_duration(effective),
                "solicitacoes": [
                    _correction_public(item)
                    for item in corrections_by_date.get(operational_date, [])
                ],
                "indicador_dia_sem_marcacao": bool(
                    snapshot
                    and expected
                    and not effective
                    and snapshot["origem"] not in {"folga", "sem_jornada"}
                ),
                "classificacao_trabalhista": "pendente_rh_juridico",
            }
        )
    return result


def summarize_mirror(mirror):
    summary = {
        "dias": len(mirror),
        "snapshots": 0,
        "dias_sem_evidencia_snapshot": 0,
        "dias_com_jornada_sem_marcacao": 0,
        "jornadas_incompletas": 0,
        "eventos_apos_horario": 0,
        "solicitacoes_por_estado": {},
        "solicitacoes_por_categoria": {},
        "classificacao_tolerancia_cinco_minutos": "pendente_confirmacao_rh",
    }
    states = defaultdict(int)
    categories = defaultdict(int)
    for day in mirror:
        summary["snapshots"] += int(day["snapshot_presente"])
        summary["dias_sem_evidencia_snapshot"] += int(not day["snapshot_presente"])
        summary["dias_com_jornada_sem_marcacao"] += int(
            day["indicador_dia_sem_marcacao"]
        )
        summary["jornadas_incompletas"] += int(
            day["estado_informativo"] == "incompleto"
        )
        summary["eventos_apos_horario"] += sum(
            1 for event in day["eventos"] if event["indicador_tempo"] == "apos_horario"
        )
        for correction in day["solicitacoes"]:
            states[correction["estado"]] += 1
            categories[correction["categoria"] or "sem_categoria"] += 1
    summary["solicitacoes_por_estado"] = dict(sorted(states.items()))
    summary["solicitacoes_por_categoria"] = dict(sorted(categories.items()))
    return summary
