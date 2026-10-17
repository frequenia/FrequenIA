"""Eventos biometricos de baixa cardinalidade, sem identificadores de titular."""

import json
import logging


LOGGER = logging.getLogger("frequenia.biometric_governance")
ALLOWED_EVENTS = frozenset({
    "enrollment", "reenrollment", "verification", "blocked", "revoked",
    "incompatible", "deletion_pending", "deleted", "deletion_failed",
    "governance_not_ready",
})
ALLOWED_DIMENSIONS = frozenset({"event", "result", "channel", "reason_code", "profile_family"})


def emit_biometric_event(event, *, result, channel="backend", reason_code="none", profile_family="arcface"):
    if event not in ALLOWED_EVENTS:
        raise ValueError("evento biometrico invalido")
    payload = {
        "event": event,
        "result": str(result)[:40],
        "channel": str(channel)[:40],
        "reason_code": str(reason_code)[:80],
        "profile_family": str(profile_family)[:40],
    }
    if set(payload) != ALLOWED_DIMENSIONS:
        raise ValueError("dimensoes biometricas invalidas")
    LOGGER.info("biometric_governance_event=%s", json.dumps(payload, sort_keys=True))
