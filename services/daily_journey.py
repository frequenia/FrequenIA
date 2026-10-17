"""Motor autoritativo de jornada diária e próxima marcação.

O relógio, a identidade, o timezone, a escala e o tipo de evento vêm do
servidor/PostgreSQL. O módulo não executa biometria nem geofence: os canais
validam essas provas antes de chamar ``confirm_expected_event``.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg2.extras

from services.effective_timekeeping import fetch_effective_events
from services.journey_observability import emit_journey_event


LOGGER = logging.getLogger(__name__)
EVENT_TYPES = {"entrada", "saida_intervalo", "retorno_intervalo", "saida"}
EVENT_LABELS = {
    "entrada": "Entrada",
    "saida_intervalo": "Saída para intervalo",
    "retorno_intervalo": "Retorno do intervalo",
    "saida": "Saída",
}


class JourneyError(RuntimeError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class PlannedEvent:
    order: int
    event_type: str
    expected_at: datetime


def _db_weekday(value: date) -> int:
    """Banco/API usam 0=domingo; ``date.weekday`` usa 0=segunda."""
    return (value.weekday() + 1) % 7


def local_wall_time(day, wall_time, timezone_name, day_offset=0):
    """Converte horário civil recusando gaps e folds de DST.

    A política explícita é fail-closed. Horários inexistentes e ambíguos não
    são normalizados; a jornada fica em ``excecao`` para correção administrativa.
    """
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise JourneyError("timezone_invalido", "Timezone da jornada inválido.", 422) from exc
    naive = datetime.combine(day + timedelta(days=day_offset), wall_time)
    candidates = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = aware.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) == naive and roundtrip.fold == fold:
            candidates.append(aware)
    unique_offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        raise JourneyError(
            "horario_local_inexistente",
            "A jornada contém horário local inexistente por mudança de offset.",
            422,
        )
    if len(unique_offsets) > 1:
        raise JourneyError(
            "horario_local_ambiguo",
            "A jornada contém horário local ambíguo por mudança de offset.",
            422,
        )
    return candidates[0].astimezone(timezone.utc)


def build_planned_events(operational_date, timezone_name, periods):
    ordered = sorted(periods, key=lambda item: item["ordem"])
    if not ordered:
        return []
    events = []
    for index, period in enumerate(ordered):
        start_type = "entrada" if index == 0 else "retorno_intervalo"
        end_type = "saida" if index == len(ordered) - 1 else "saida_intervalo"
        events.append(
            PlannedEvent(
                len(events) + 1,
                start_type,
                local_wall_time(operational_date, period["inicio"], timezone_name),
            )
        )
        events.append(
            PlannedEvent(
                len(events) + 1,
                end_type,
                local_wall_time(
                    operational_date,
                    period["fim"],
                    timezone_name,
                    int(period.get("fim_dia_offset") or 0),
                ),
            )
        )
    for previous, current in zip(events, events[1:]):
        if current.expected_at <= previous.expected_at:
            raise JourneyError(
                "periodos_inconsistentes",
                "Os períodos da jornada não formam uma sequência válida.",
                422,
            )
    return events


def _official_now(cursor):
    cursor.execute("SELECT clock_timestamp() AS agora")
    return cursor.fetchone()["agora"]


def _resolve_schedule(cursor, company_id, employee_id, operational_date, default_timezone="UTC"):
    cursor.execute(
        """SELECT ed.id AS escala_id, ed.tipo AS escala_tipo, ed.origem,
                  ed.turno_id, t.timezone, t.nome AS turno_nome
           FROM escalas_diarias ed
           LEFT JOIN turnos t ON t.id=ed.turno_id AND t.empresa_id=ed.empresa_id
           WHERE ed.empresa_id=%s AND ed.funcionario_id=%s
             AND ed.data_operacional=%s AND ed.cancelado_at IS NULL
           ORDER BY ed.created_at DESC, ed.id DESC LIMIT 1""",
        (company_id, employee_id, operational_date),
    )
    schedule = cursor.fetchone()
    if schedule:
        if schedule["escala_tipo"] == "folga":
            return {
                "origin": "folga", "timezone": default_timezone, "turno_id": None,
                "escala_id": schedule["escala_id"], "assignment_id": None, "periods": [],
                "turn_name": None, "valid_from": None, "valid_to": None,
            }
        source = schedule["origem"] if schedule["origem"] in {"troca", "ajuste"} else "escala"
        turn_id = schedule["turno_id"]
        timezone_name = schedule["timezone"]
        turn_name = schedule["turno_nome"]
        assignment_id = None
        valid_from = operational_date
        valid_to = operational_date
    else:
        cursor.execute(
            """SELECT ft.id AS atribuicao_id, ft.turno_id, ft.vigencia_inicio,
                      ft.vigencia_fim, t.timezone, t.nome AS turno_nome
               FROM funcionarios_turnos ft
               JOIN turnos t ON t.id=ft.turno_id AND t.empresa_id=ft.empresa_id
               WHERE ft.empresa_id=%s AND ft.funcionario_id=%s
                 AND ft.vigencia_inicio <= %s
                 AND (ft.vigencia_fim IS NULL OR ft.vigencia_fim >= %s)
                 AND t.status='ativo'
               ORDER BY ft.vigencia_inicio DESC, ft.created_at DESC, ft.id DESC LIMIT 1""",
            (company_id, employee_id, operational_date, operational_date),
        )
        assignment = cursor.fetchone()
        if not assignment:
            return {
                "origin": "sem_jornada", "timezone": default_timezone, "turno_id": None,
                "escala_id": None, "assignment_id": None, "periods": [],
                "turn_name": None, "valid_from": None, "valid_to": None,
            }
        source = "turno"
        turn_id = assignment["turno_id"]
        timezone_name = assignment["timezone"]
        turn_name = assignment["turno_nome"]
        assignment_id = assignment["atribuicao_id"]
        valid_from = assignment["vigencia_inicio"]
        valid_to = assignment["vigencia_fim"]

    cursor.execute(
        """SELECT id,ordem,inicio,fim,fim_dia_offset
           FROM periodos_turno
           WHERE empresa_id=%s AND turno_id=%s AND dia_semana=%s
           ORDER BY ordem,id""",
        (company_id, turn_id, _db_weekday(operational_date)),
    )
    periods = cursor.fetchall()
    if not periods:
        return {
            "origin": "sem_jornada", "timezone": timezone_name,
            "turno_id": None, "escala_id": schedule["escala_id"] if schedule else None,
            "assignment_id": assignment_id, "periods": [], "turn_name": None,
            "valid_from": valid_from, "valid_to": valid_to,
        }
    return {
        "origin": source, "timezone": timezone_name, "turno_id": turn_id,
        "escala_id": schedule["escala_id"] if schedule else None,
        "assignment_id": assignment_id, "periods": periods,
        "turn_name": turn_name, "valid_from": valid_from, "valid_to": valid_to,
    }


def resolve_schedule_for_date(cursor, company_id, employee_id, operational_date, default_timezone="UTC"):
    resolved = _resolve_schedule(cursor, company_id, employee_id, operational_date, default_timezone)
    return {
        "origem": resolved["origin"],
        "folga": resolved["origin"] == "folga",
        "turno": ({
            "id": str(resolved["turno_id"]), "nome": resolved["turn_name"],
            "timezone": resolved["timezone"], "status": "ativo",
        } if resolved["turno_id"] else None),
        "vigencia": {
            "inicio": resolved["valid_from"].isoformat() if resolved["valid_from"] else None,
            "fim": resolved["valid_to"].isoformat() if resolved["valid_to"] else None,
        },
        "periodos": [{
            "id": str(item["id"]), "dia_semana": _db_weekday(operational_date),
            "ordem": item["ordem"], "inicio": item["inicio"].strftime("%H:%M"),
            "fim": item["fim"].strftime("%H:%M"),
            "fim_dia_offset": item["fim_dia_offset"],
        } for item in resolved["periods"]],
    }


def _operational_date_for_now(cursor, company_id, employee_id, now, default_timezone):
    """Resolve a data local sem assumir que a data UTC é a data da escala.

    Avaliar os três dias possíveis evita perder uma exceção específica quando
    o instante está próximo da meia-noite e o turno/escala usa outro offset.
    """
    utc_day = now.astimezone(timezone.utc).date()
    fallback_zone = ZoneInfo(default_timezone)
    for candidate in (utc_day - timedelta(days=1), utc_day, utc_day + timedelta(days=1)):
        resolved = _resolve_schedule(cursor, company_id, employee_id, candidate, default_timezone)
        try:
            zone = ZoneInfo(resolved["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise JourneyError("timezone_invalido", "Timezone da jornada inválido.", 422) from exc
        if now.astimezone(zone).date() == candidate:
            return candidate
    return now.astimezone(fallback_zone).date()


def _snapshot_row(cursor, company_id, employee_id, operational_date):
    cursor.execute(
        """SELECT * FROM jornadas_diarias
           WHERE empresa_id=%s AND funcionario_id=%s AND data_operacional=%s""",
        (company_id, employee_id, operational_date),
    )
    return cursor.fetchone()


def _snapshot_events(cursor, company_id, journey_id):
    cursor.execute(
        """SELECT id,ordem,tipo,instante_esperado,marcacao_id,cumprido_at
           FROM jornada_eventos_esperados
           WHERE empresa_id=%s AND jornada_id=%s ORDER BY ordem,id""",
        (company_id, journey_id),
    )
    return cursor.fetchall()


def materialize_snapshot(cursor, company_id, employee_id, operational_date, *, default_timezone="UTC", actor_user_id=None):
    existing = _snapshot_row(cursor, company_id, employee_id, operational_date)
    if existing:
        return existing, _snapshot_events(cursor, company_id, existing["id"]), False
    resolved = _resolve_schedule(cursor, company_id, employee_id, operational_date, default_timezone)
    events = build_planned_events(
        operational_date, resolved["timezone"], resolved["periods"]
    ) if resolved["periods"] else []
    cursor.execute(
        """INSERT INTO jornadas_diarias
           (empresa_id,funcionario_id,data_operacional,timezone,origem,turno_id,
            escala_diaria_id,atribuicao_turno_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (empresa_id,funcionario_id,data_operacional) DO NOTHING
           RETURNING *""",
        (
            company_id, employee_id, operational_date, resolved["timezone"],
            resolved["origin"], resolved["turno_id"], resolved["escala_id"],
            resolved["assignment_id"],
        ),
    )
    snapshot = cursor.fetchone()
    created = snapshot is not None
    if created:
        for event in events:
            cursor.execute(
                """INSERT INTO jornada_eventos_esperados
                   (empresa_id,jornada_id,ordem,tipo,instante_esperado)
                   VALUES (%s,%s,%s,%s,%s)""",
                (company_id, snapshot["id"], event.order, event.event_type, event.expected_at),
            )
        if actor_user_id:
            cursor.execute(
                """INSERT INTO auditoria
                   (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
                   VALUES (%s,%s,'jornada.snapshot_materializado','jornada',%s,
                           clock_timestamp(),%s)""",
                (
                    company_id, actor_user_id, snapshot["id"],
                    psycopg2.extras.Json({
                        "origem": resolved["origin"], "eventos": len(events), "versao": 1,
                    }),
                ),
            )
    else:
        snapshot = _snapshot_row(cursor, company_id, employee_id, operational_date)
    return snapshot, _snapshot_events(cursor, company_id, snapshot["id"]), created


def _effective_matches(cursor, company_id, employee_id, events, grace_hours):
    if not events:
        return []
    start = events[0]["instante_esperado"] - timedelta(hours=grace_hours)
    end = events[-1]["instante_esperado"] + timedelta(hours=grace_hours)
    effective = fetch_effective_events(cursor, company_id, employee_id, start, end)
    matched = []
    position = 0
    for event in events:
        direct = event.get("marcacao_id")
        found = None
        if direct:
            found = next(
                (item for item in effective if str(item.get("marcacao_original_id")) == str(direct)),
                None,
            )
        if found is None:
            for index in range(position, len(effective)):
                if effective[index]["tipo"] == event["tipo"]:
                    found = effective[index]
                    position = index + 1
                    break
        if found is None:
            break
        matched.append(found)
    return matched


def _serialize(snapshot, events, matched, now):
    origin = snapshot["origem"]
    total = len(events)
    completed = len(matched)
    if origin == "folga":
        state, reason = "folga", "folga_programada"
    elif origin == "sem_jornada" or total == 0:
        state, reason = "sem_jornada", "jornada_nao_configurada"
    elif completed >= total:
        state, reason = "concluida", "jornada_concluida"
    else:
        state = "em_andamento" if completed else "aguardando"
        reason = None
    next_event = events[completed] if completed < total else None
    delta = None
    if next_event:
        delta = int((now - next_event["instante_esperado"]).total_seconds() // 60)
    return {
        "snapshot_id": str(snapshot["id"]),
        "versao": snapshot["versao"],
        "data_operacional": snapshot["data_operacional"].isoformat(),
        "timezone": snapshot["timezone"],
        "origem": origin,
        "estado": state,
        "motivo": reason,
        "ordem": next_event["ordem"] if next_event else completed,
        "total_eventos": total,
        "proximo": (
            {
                "evento_id": str(next_event["id"]),
                "tipo": next_event["tipo"],
                "label": EVENT_LABELS[next_event["tipo"]],
                "horario_esperado": next_event["instante_esperado"].isoformat(),
                "ordem": next_event["ordem"],
                "diferenca_minutos": delta,
                "situacao_tempo": "atrasado" if delta > 0 else ("adiantado" if delta < 0 else "no_horario"),
            }
            if next_event else None
        ),
    }


def resolve_next_event(cursor, company_id, employee_id, *, now=None, default_timezone="UTC", grace_hours=12, materialize=True, actor_user_id=None):
    now = now or _official_now(cursor)
    # Uma jornada anterior materializada e ainda incompleta tem precedência.
    cursor.execute(
        """SELECT * FROM jornadas_diarias
           WHERE empresa_id=%s AND funcionario_id=%s
             AND data_operacional >= (clock_timestamp() AT TIME ZONE 'UTC')::date - 2
           ORDER BY data_operacional DESC LIMIT 3""",
        (company_id, employee_id),
    )
    for snapshot in cursor.fetchall():
        events = _snapshot_events(cursor, company_id, snapshot["id"])
        matched = _effective_matches(cursor, company_id, employee_id, events, grace_hours)
        if events and len(matched) < len(events) and now <= events[-1]["instante_esperado"] + timedelta(hours=grace_hours):
            result = _serialize(snapshot, events, matched, now)
            emit_journey_event("journey_resolved", origin=result["origem"], state=result["estado"], result="previous_open")
            return result

    # Descobre a data local pelo timezone da regra aplicável, nunca pelo cliente.
    try:
        local_day = _operational_date_for_now(
            cursor, company_id, employee_id, now, default_timezone,
        )
    except ZoneInfoNotFoundError as exc:
        raise JourneyError("timezone_invalido", "Timezone da jornada inválido.", 422) from exc
    if materialize:
        snapshot, events, _ = materialize_snapshot(
            cursor, company_id, employee_id, local_day,
            default_timezone=default_timezone, actor_user_id=actor_user_id,
        )
    else:
        snapshot = _snapshot_row(cursor, company_id, employee_id, local_day)
        if not snapshot:
            resolved = _resolve_schedule(cursor, company_id, employee_id, local_day, default_timezone)
            planned = build_planned_events(local_day, resolved["timezone"], resolved["periods"]) if resolved["periods"] else []
            return {
                "snapshot_id": None, "versao": 1, "data_operacional": local_day.isoformat(),
                "timezone": resolved["timezone"], "origem": resolved["origin"],
                "estado": "folga" if resolved["origin"] == "folga" else ("sem_jornada" if not planned else "aguardando"),
                "motivo": "folga_programada" if resolved["origin"] == "folga" else ("jornada_nao_configurada" if not planned else None),
                "ordem": 1 if planned else 0, "total_eventos": len(planned),
                "proximo": ({"evento_id": None, "tipo": planned[0].event_type, "label": EVENT_LABELS[planned[0].event_type], "horario_esperado": planned[0].expected_at.isoformat(), "ordem": 1, "diferenca_minutos": int((now-planned[0].expected_at).total_seconds()//60), "situacao_tempo": "informativo"} if planned else None),
            }
        events = _snapshot_events(cursor, company_id, snapshot["id"])
    matched = _effective_matches(cursor, company_id, employee_id, events, grace_hours)
    result = _serialize(snapshot, events, matched, now)
    emit_journey_event("journey_resolved", origin=result["origem"], state=result["estado"], result="resolved")
    return result


def _record_order_exception(cursor, company_id, employee_id, decision, key, channel, facial_attempt_id, legacy_type, actor_user_id):
    snapshot_id = decision.get("snapshot_id")
    event_id = decision.get("proximo", {}).get("evento_id") if decision.get("proximo") else None
    reason = decision.get("motivo") or "tipo_legado_divergente"
    cursor.execute(
        """INSERT INTO tentativas_jornada
           (empresa_id,funcionario_id,jornada_id,evento_esperado_id,tentativa_facial_id,
            chave_idempotencia,canal,resultado,motivo_codigo,tipo_legado)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'analise',%s,%s)
           ON CONFLICT (empresa_id,chave_idempotencia) DO NOTHING RETURNING id""",
        (company_id, employee_id, snapshot_id, event_id, facial_attempt_id, key, channel, reason, legacy_type),
    )
    attempt = cursor.fetchone()
    cursor.execute(
        """INSERT INTO ocorrencias
           (empresa_id,funcionario_id,tentativa_facial_id,tipo,descricao,estado,
            primeira_ocorrencia_at,jornada_id,jornada_evento_id,data_operacional,motivo_codigo)
           VALUES (%s,%s,%s,'ordem_invalida','Tentativa enviada para análise.','aberta',
                   clock_timestamp(),%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id""",
        (company_id, employee_id, facial_attempt_id, snapshot_id, event_id, decision["data_operacional"], reason),
    )
    occurrence = cursor.fetchone()
    entity_id = occurrence["id"] if occurrence else (snapshot_id or employee_id)
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
           VALUES (%s,%s,'jornada.excecao_ordem','jornada',%s,clock_timestamp(),%s)""",
        (company_id, actor_user_id, entity_id, psycopg2.extras.Json({"motivo": reason, "canal": channel, "possui_evento": bool(event_id)})),
    )
    return str(occurrence["id"]) if occurrence else None


def confirm_expected_event(cursor, company_id, employee_id, *, key, channel, facial_attempt_id, actor_user_id, legacy_type=None, marking_fields=None, default_timezone="UTC", grace_hours=12, minimum_interval_seconds=60):
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"{company_id}:{employee_id}",))
    cursor.execute(
        """SELECT id,funcionario_id,tentativa_facial_id,tipo,origem,estado,instante,
                  chave_idempotencia,canal,precisao_metros,distancia_unidade_metros,jornada_evento_id
           FROM marcacoes WHERE empresa_id=%s AND chave_idempotencia=%s""",
        (company_id, key),
    )
    existing = cursor.fetchone()
    if existing:
        same = str(existing["funcionario_id"]) == str(employee_id) and existing.get("canal") == channel and str(existing.get("tentativa_facial_id")) == str(facial_attempt_id)
        if not same:
            raise JourneyError("idempotencia_conflitante", "Chave de idempotência indisponível.")
        return {"marking": existing, "reused": True, "decision": None}

    now = _official_now(cursor)
    try:
        decision = resolve_next_event(
            cursor, company_id, employee_id, now=now, default_timezone=default_timezone,
            grace_hours=grace_hours, materialize=True, actor_user_id=actor_user_id,
        )
    except JourneyError as exc:
        if exc.code not in {
            "timezone_invalido", "horario_local_inexistente",
            "horario_local_ambiguo", "periodos_inconsistentes",
        }:
            raise
        decision = {
            "snapshot_id": None, "versao": 1,
            "data_operacional": now.astimezone(timezone.utc).date().isoformat(),
            "timezone": default_timezone, "origem": "sem_jornada",
            "estado": "excecao", "motivo": exc.code,
            "ordem": 0, "total_eventos": 0, "proximo": None,
        }
    next_event = decision.get("proximo")
    blocked = decision["estado"] in {"folga", "sem_jornada", "concluida", "excecao"} or not next_event
    if legacy_type and legacy_type not in EVENT_TYPES:
        raise JourneyError("tipo_legado_invalido", "Tipo legado inválido.", 400)
    if legacy_type and next_event and legacy_type != next_event["tipo"]:
        decision["motivo"] = "tipo_legado_divergente"
        blocked = True
    if blocked:
        occurrence_id = _record_order_exception(
            cursor, company_id, employee_id, decision, key, channel,
            facial_attempt_id, legacy_type, actor_user_id,
        )
        code = decision.get("motivo") or "sem_evento_esperado"
        emit_journey_event("journey_order_exception", origin=decision["origem"], state=decision["estado"], result="analysis", reason=code)
        return {"marking": None, "reused": False, "decision": decision, "occurrence_id": occurrence_id, "code": code}

    cursor.execute(
        """SELECT id,tipo,instante FROM marcacoes
           WHERE empresa_id=%s AND funcionario_id=%s
             AND instante >= clock_timestamp()-(%s*interval '1 second')
           ORDER BY instante DESC,id DESC LIMIT 1""",
        (company_id, employee_id, minimum_interval_seconds),
    )
    recent = cursor.fetchone()
    if recent:
        raise JourneyError("marcacao_recente", "Já existe uma marcação registrada recentemente.")

    fields = dict(marking_fields or {})
    cursor.execute(
        """INSERT INTO marcacoes
           (empresa_id,funcionario_id,tentativa_facial_id,unidade_id,instante,tipo,
            origem,estado,chave_idempotencia,canal,latitude,longitude,precisao_metros,
            distancia_unidade_metros,localizacao_capturada_at,endereco_localizacao,jornada_evento_id)
           VALUES (%s,%s,%s,%s,clock_timestamp(),%s,'facial','confirmada',%s,%s,
                   %s,%s,%s,%s,%s,%s,%s)
           RETURNING id,funcionario_id,tentativa_facial_id,tipo,origem,estado,instante,
                     chave_idempotencia,canal,precisao_metros,distancia_unidade_metros,jornada_evento_id""",
        (
            company_id, employee_id, facial_attempt_id, fields.get("unidade_id"),
            next_event["tipo"], key, channel, fields.get("latitude"), fields.get("longitude"),
            fields.get("precisao_metros"), fields.get("distancia_unidade_metros"),
            fields.get("localizacao_capturada_at"), fields.get("endereco_localizacao"),
            next_event["evento_id"],
        ),
    )
    marking = cursor.fetchone()
    delta = next_event.get("diferenca_minutos", 0)
    timing = "late" if delta > 0 else ("early" if delta < 0 else "on_time")
    emit_journey_event("marking_confirmed", origin=decision["origem"], state=decision["estado"], result="created", event_type=next_event["tipo"], timing_bucket=timing)
    cursor.execute(
        """UPDATE jornada_eventos_esperados
           SET marcacao_id=%s,cumprido_at=clock_timestamp()
           WHERE id=%s AND empresa_id=%s AND marcacao_id IS NULL""",
        (marking["id"], next_event["evento_id"], company_id),
    )
    cursor.execute(
        """INSERT INTO tentativas_jornada
           (empresa_id,funcionario_id,jornada_id,evento_esperado_id,tentativa_facial_id,
            chave_idempotencia,canal,resultado,motivo_codigo,tipo_legado)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'confirmada','evento_confirmado',%s)""",
        (company_id, employee_id, decision["snapshot_id"], next_event["evento_id"], facial_attempt_id, key, channel, legacy_type),
    )
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
           VALUES (%s,%s,'jornada.evento_vinculado','marcacao',%s,clock_timestamp(),%s)""",
        (company_id, actor_user_id, marking["id"], psycopg2.extras.Json({"tipo": next_event["tipo"], "ordem": next_event["ordem"], "canal": channel})),
    )
    return {"marking": marking, "reused": False, "decision": decision}
