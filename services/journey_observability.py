"""Eventos operacionais sanitizados e de baixa cardinalidade da jornada."""

import json
import logging


LOGGER = logging.getLogger("frequenia.journey")
ALLOWED = {"event", "origin", "state", "result", "event_type", "timing_bucket", "reason"}


def emit_journey_event(event, **values):
    payload = {"event": event}
    for key, value in values.items():
        if key in ALLOWED and value is not None:
            payload[key] = str(value)[:64]
    LOGGER.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))
