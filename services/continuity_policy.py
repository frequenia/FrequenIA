"""Política server-side para exercícios de continuidade, sem promessas de produção."""
from dataclasses import dataclass
import os


class ContinuityPolicyError(ValueError):
    pass


def _integer(name, default, minimum, maximum):
    try:
        value=int(os.getenv(name,str(default)))
    except (TypeError,ValueError) as exc:
        raise ContinuityPolicyError(f"Configuração inválida: {name}.") from exc
    if not minimum <= value <= maximum:
        raise ContinuityPolicyError(f"Configuração fora do limite: {name}.")
    return value


@dataclass(frozen=True)
class ContinuityPolicy:
    rpo_seconds: int
    rto_seconds: int
    frequency_hours: int
    retention_days: int
    exercise_window_minutes: int
    max_set_bytes: int
    production_approved: bool
    approval_reference: str | None

    @property
    def production_status(self):
        return "aprovado" if self.production_approved else "aprovacao_corporativa_pendente"


def load_continuity_policy(environment=None):
    environment=(environment or os.getenv("APP_ENV","development")).strip().lower()
    approved=os.getenv("CONTINUITY_PRODUCTION_APPROVED","false").strip().lower()=="true"
    reference=os.getenv("CONTINUITY_APPROVAL_REFERENCE","").strip() or None
    if approved and (environment not in {"production","prod"} or not reference):
        raise ContinuityPolicyError("Aprovação de produção exige ambiente de produção e referência formal.")
    return ContinuityPolicy(
        rpo_seconds=_integer("CONTINUITY_RPO_SECONDS",3600,60,604800),
        rto_seconds=_integer("CONTINUITY_RTO_SECONDS",7200,60,604800),
        frequency_hours=_integer("CONTINUITY_FREQUENCY_HOURS",24,1,8760),
        retention_days=_integer("CONTINUITY_BACKUP_RETENTION_DAYS",30,1,3650),
        exercise_window_minutes=_integer("CONTINUITY_EXERCISE_WINDOW_MINUTES",60,5,1440),
        max_set_bytes=_integer("CONTINUITY_MAX_SET_BYTES",1073741824,1048576,1099511627776),
        production_approved=approved,
        approval_reference=reference,
    )
