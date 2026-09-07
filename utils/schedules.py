from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


WEEK_MINUTES = 7 * 24 * 60


def parse_iso_date(value, field_name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve usar o formato AAAA-MM-DD.") from exc


def parse_optional_iso_date(value, field_name):
    if value in (None, ""):
        return None
    return parse_iso_date(value, field_name)


def parse_hhmm(value, field_name):
    text = str(value or "")
    if len(text) != 5 or text[2] != ":":
        raise ValueError(f"{field_name} deve usar o formato HH:MM.")
    try:
        parsed = time.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} deve usar o formato HH:MM.") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError(f"{field_name} deve usar o formato HH:MM.")
    return parsed


def validate_timezone(value):
    timezone_name = str(value or "America/Sao_Paulo").strip()
    if not timezone_name:
        raise ValueError("Timezone é obrigatório.")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone inválido.") from exc
    return timezone_name


def _small_integer(value, field_name, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} inválido.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} inválido.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} inválido.")
    return parsed


def _minutes(value):
    return value.hour * 60 + value.minute


def _circular_segments(period):
    start = period["dia_semana"] * 1440 + _minutes(period["inicio"])
    end = (
        period["dia_semana"] * 1440
        + _minutes(period["fim"])
        + period["fim_dia_offset"] * 1440
    )
    if end <= WEEK_MINUTES:
        return [(start, end)]
    return [(start, WEEK_MINUTES), (0, end - WEEK_MINUTES)]


def validate_periods(raw_periods):
    if not isinstance(raw_periods, list) or not raw_periods:
        raise ValueError("Informe ao menos um período para o turno.")

    periods = []
    for index, raw in enumerate(raw_periods, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Período {index} inválido.")

        day = _small_integer(raw.get("dia_semana"), "Dia da semana", 0, 6)
        order = _small_integer(raw.get("ordem"), "Ordem", 1, 32767)
        offset = _small_integer(
            raw.get("fim_dia_offset", 0), "Offset do fim", 0, 1
        )
        start_time = parse_hhmm(raw.get("inicio"), "Início")
        end_time = parse_hhmm(raw.get("fim"), "Fim")
        duration = _minutes(end_time) + offset * 1440 - _minutes(start_time)

        if duration <= 0 or duration >= 1440:
            raise ValueError(
                "Cada período deve terminar depois do início e durar menos de 24 horas."
            )

        periods.append(
            {
                "dia_semana": day,
                "ordem": order,
                "inicio": start_time,
                "fim": end_time,
                "fim_dia_offset": offset,
            }
        )

    periods.sort(key=lambda item: (item["dia_semana"], item["ordem"]))
    by_day = {}
    for period in periods:
        by_day.setdefault(period["dia_semana"], []).append(period)

    for day_periods in by_day.values():
        orders = [period["ordem"] for period in day_periods]
        if orders != list(range(1, len(day_periods) + 1)):
            raise ValueError("A ordem dos períodos de cada dia deve ser sequencial.")
        starts = [_minutes(period["inicio"]) for period in day_periods]
        if starts != sorted(starts):
            raise ValueError("A ordem dos períodos deve seguir seus horários de início.")

    segments = []
    for period in periods:
        segments.extend(_circular_segments(period))
    segments.sort()
    for previous, current in zip(segments, segments[1:]):
        if current[0] < previous[1]:
            raise ValueError("Os períodos do turno não podem se sobrepor.")

    return periods


def format_time(value):
    return value.strftime("%H:%M")


def serialize_period(period):
    return {
        "id": str(period["id"]) if period.get("id") else None,
        "dia_semana": period["dia_semana"],
        "ordem": period["ordem"],
        "inicio": format_time(period["inicio"]),
        "fim": format_time(period["fim"]),
        "fim_dia_offset": period["fim_dia_offset"],
    }
