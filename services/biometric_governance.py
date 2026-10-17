"""Governanca autoritativa do ciclo biometrico.

O modulo nunca decide base legal. Ele exige uma politica aprovada, versionada e
tenant-scoped antes de novas operacoes sensiveis. Material facial nao e emitido
em logs, auditoria ou respostas.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

import psycopg2.extras

from services.face_service import EMBEDDING_DIMENSION, MODEL_NAME, MODEL_VERSION


PURPOSE = "registro_ponto_1a1"
LOW_CARDINALITY_STATES = frozenset(
    {"ativa", "bloqueada", "revogada", "exclusao_pendente", "eliminada"}
)
MUTATIONS = frozenset(
    {"bloquear", "revogar", "solicitar_exclusao", "criar_hold", "cancelar_hold"}
)
REASON_RE = re.compile(r"^[a-z0-9_.-]{1,100}$")


class BiometricGovernanceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class GovernanceContext:
    policy_id: str
    policy_version: str
    notice_version: str
    purpose: str
    retention_days: int
    service_channel: str
    profile_id: str
    profile_version: str
    model: str
    model_version: str
    dimension: int
    metric: str
    threshold: float
    liveness_version: str


def _validate_reason(reason: Any) -> str:
    value = str(reason or "").strip().lower()
    if not REASON_RE.fullmatch(value):
        raise BiometricGovernanceError(
            "motivo_invalido", "Informe um motivo tecnico valido.", 400
        )
    return value


def _validate_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not 8 <= len(key) <= 200 or any(ord(char) < 32 for char in key):
        raise BiometricGovernanceError(
            "idempotencia_invalida", "Chave de idempotencia invalida.", 400
        )
    return key


def resolve_governance(cursor, company_id: str, *, lock: bool = False) -> GovernanceContext:
    """Resolve politica e perfil vigentes pelo relogio do PostgreSQL."""
    lock_clause = " FOR SHARE OF p, t" if lock else ""
    cursor.execute(
        """
        SELECT p.id AS policy_id, p.versao AS policy_version,
               p.versao_aviso AS notice_version, p.finalidade,
               p.retencao_dias, p.canal_atendimento,
               t.id AS profile_id, t.versao AS profile_version,
               t.modelo, t.versao_modelo, t.dimensao, t.metrica,
               t.limiar, t.versao_liveness
        FROM politicas_biometricas p
        JOIN perfis_tecnicos_biometricos t
          ON t.empresa_id = p.empresa_id AND t.finalidade = p.finalidade
        WHERE p.empresa_id = %s
          AND p.finalidade = %s
          AND p.estado = 'aprovada'
          AND p.vigencia_inicio <= clock_timestamp()
          AND (p.vigencia_fim IS NULL OR p.vigencia_fim > clock_timestamp())
          AND t.estado = 'ativo'
          AND t.vigencia_inicio <= clock_timestamp()
          AND (t.vigencia_fim IS NULL OR t.vigencia_fim > clock_timestamp())
        ORDER BY p.vigencia_inicio DESC, t.vigencia_inicio DESC
        LIMIT 1
        """ + lock_clause,
        (company_id, PURPOSE),
    )
    row = cursor.fetchone()
    if not row:
        raise BiometricGovernanceError(
            "governanca_biometrica_pendente",
            "Politica biometrica ou perfil tecnico vigente indisponivel.",
            503,
        )
    threshold = float(row["limiar"])
    if not math.isfinite(threshold) or not 0 < threshold <= 2:
        raise BiometricGovernanceError(
            "perfil_biometrico_invalido", "Perfil tecnico biometrico invalido.", 503
        )
    if int(row["dimensao"]) != EMBEDDING_DIMENSION or row["metrica"] != "cosine_distance":
        raise BiometricGovernanceError(
            "perfil_biometrico_incompativel",
            "Recadastro biometrico necessario.",
            409,
        )
    return GovernanceContext(
        policy_id=str(row["policy_id"]),
        policy_version=row["policy_version"],
        notice_version=row["notice_version"],
        purpose=row["finalidade"],
        retention_days=int(row["retencao_dias"]),
        service_channel=row["canal_atendimento"],
        profile_id=str(row["profile_id"]),
        profile_version=row["profile_version"],
        model=row["modelo"],
        model_version=row["versao_modelo"],
        dimension=int(row["dimensao"]),
        metric=row["metrica"],
        threshold=threshold,
        liveness_version=row["versao_liveness"],
    )


def resolve_verification_material(cursor, company_id: str, employee_id: str):
    """Trava o vinculo e retorna somente material 1:1 governado e compativel."""
    cursor.execute(
        """SELECT id, status FROM funcionarios
           WHERE empresa_id=%s AND id=%s FOR SHARE""",
        (company_id, employee_id),
    )
    employee = cursor.fetchone()
    if not employee or employee["status"] != "ativo":
        raise BiometricGovernanceError(
            "vinculo_nao_operacional", "Verificacao biometrica indisponivel.", 409
        )
    governance = resolve_governance(cursor, company_id, lock=True)
    cursor.execute(
        """
        SELECT b.id, b.embedding, b.modelo, b.versao_modelo,
               b.politica_biometrica_id, b.perfil_tecnico_id
        FROM biometrias b
        WHERE b.empresa_id=%s AND b.funcionario_id=%s AND b.status='ativa'
        ORDER BY b.created_at DESC, b.id DESC LIMIT 1 FOR SHARE
        """,
        (company_id, employee_id),
    )
    biometric = cursor.fetchone()
    if not biometric:
        return None, governance
    compatible = (
        str(biometric["politica_biometrica_id"] or "") == governance.policy_id
        and str(biometric["perfil_tecnico_id"] or "") == governance.profile_id
        and biometric["modelo"] == governance.model
        and biometric["versao_modelo"] == governance.model_version
        and biometric["embedding"] is not None
    )
    if not compatible:
        _audit(
            cursor,
            company_id,
            None,
            "biometria.incompatibilidade",
            biometric["id"],
            {"codigo": "perfil_incompativel", "perfil_versao": governance.profile_version},
        )
        raise BiometricGovernanceError(
            "recadastro_biometrico_necessario", "Recadastro biometrico necessario.", 409
        )
    return biometric, governance


def _audit(cursor, company_id, actor_id, action, entity_id, metadata):
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,ocorrido_at,metadados)
           VALUES (%s,%s,%s,'biometria',%s,clock_timestamp(),%s::jsonb)""",
        (company_id, actor_id, action, entity_id, json.dumps(metadata, sort_keys=True)),
    )


def record_lifecycle(
    cursor, *, company_id, employee_id, biometric_id, actor_id, action,
    previous, target, reason, policy_id=None, profile_id=None,
):
    reason = _validate_reason(reason)
    cursor.execute(
        """INSERT INTO historico_ciclo_biometrico
           (empresa_id,biometria_id,funcionario_id,ator_usuario_id,acao,
            estado_anterior,estado_novo,motivo_codigo,politica_biometrica_id,
            perfil_tecnico_id,ocorrido_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())""",
        (company_id, biometric_id, employee_id, actor_id, action, previous,
         target, reason, policy_id, profile_id),
    )
    _audit(
        cursor, company_id, actor_id, f"biometria.{action}", biometric_id,
        {"estado_anterior": previous, "estado_novo": target,
         "motivo_codigo": reason, "politica_id": str(policy_id) if policy_id else None,
         "perfil_id": str(profile_id) if profile_id else None},
    )


def transition_biometric(
    cursor, *, company_id, employee_id, actor_id, operation, reason,
    idempotency_key,
):
    if operation not in MUTATIONS - {"criar_hold", "cancelar_hold"}:
        raise BiometricGovernanceError("operacao_invalida", "Operacao invalida.", 400)
    reason = _validate_reason(reason)
    key = _validate_idempotency_key(idempotency_key)
    cursor.execute(
        """SELECT biometria_id,operacao,estado_resultante FROM operacoes_biometricas
           WHERE empresa_id=%s AND chave_idempotencia=%s""",
        (company_id, key),
    )
    prior = cursor.fetchone()
    if prior:
        if prior["operacao"] != operation:
            raise BiometricGovernanceError(
                "idempotencia_conflitante", "Chave de idempotencia indisponivel.", 409
            )
        return {"biometria_id": str(prior["biometria_id"]),
                "status": prior["estado_resultante"], "reutilizada": True}
    cursor.execute(
        """SELECT id,status,politica_biometrica_id,perfil_tecnico_id
           FROM biometrias WHERE empresa_id=%s AND funcionario_id=%s
           ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE""",
        (company_id, employee_id),
    )
    row = cursor.fetchone()
    if not row:
        raise BiometricGovernanceError("biometria_nao_encontrada", "Funcionario nao encontrado.", 404)
    transitions = {
        "bloquear": ({"ativa"}, "bloqueada"),
        "revogar": ({"ativa", "bloqueada"}, "revogada"),
        "solicitar_exclusao": ({"ativa", "bloqueada", "revogada"}, "exclusao_pendente"),
    }
    allowed, target = transitions[operation]
    if row["status"] == target:
        pass
    elif row["status"] not in allowed:
        raise BiometricGovernanceError(
            "transicao_biometrica_invalida", "Transicao biometrica invalida.", 409
        )
    else:
        assignments = ["status=%s", "motivo_codigo=%s", "updated_at=clock_timestamp()"]
        if target == "bloqueada":
            assignments.append("bloqueada_at=clock_timestamp()")
        elif target == "revogada":
            assignments.append("revoked_at=clock_timestamp()")
        elif target == "exclusao_pendente":
            assignments.append("exclusao_solicitada_at=clock_timestamp()")
            cursor.execute(
                """SELECT retencao_dias FROM politicas_biometricas
                   WHERE empresa_id=%s AND id=%s""",
                (company_id, row["politica_biometrica_id"]),
            )
            policy = cursor.fetchone()
            if not policy or policy["retencao_dias"] is None:
                raise BiometricGovernanceError(
                    "retencao_pendente", "Politica de retencao indisponivel.", 409
                )
            assignments.append(
                "eliminacao_elegivel_at=clock_timestamp() + (%s * interval '1 day')"
            )
        parameters = [target, reason]
        if target == "exclusao_pendente":
            parameters.append(int(policy["retencao_dias"]))
        parameters.extend([company_id, row["id"]])
        cursor.execute(
            f"UPDATE biometrias SET {', '.join(assignments)} WHERE empresa_id=%s AND id=%s",
            tuple(parameters),
        )
        record_lifecycle(
            cursor, company_id=company_id, employee_id=employee_id,
            biometric_id=row["id"], actor_id=actor_id, action=operation,
            previous=row["status"], target=target, reason=reason,
            policy_id=row["politica_biometrica_id"], profile_id=row["perfil_tecnico_id"],
        )
    cursor.execute(
        """INSERT INTO operacoes_biometricas
           (empresa_id,biometria_id,funcionario_id,chave_idempotencia,operacao,
            motivo_codigo,ator_usuario_id,estado_resultante)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (company_id, row["id"], employee_id, key, operation, reason, actor_id, target),
    )
    return {"biometria_id": str(row["id"]), "status": target, "reutilizada": False}


def manage_hold(
    cursor, *, company_id, employee_id, actor_id, operation, reason,
    reference, idempotency_key, expires_at=None,
):
    if operation not in {"criar_hold", "cancelar_hold"}:
        raise BiometricGovernanceError("operacao_invalida", "Operacao invalida.", 400)
    reason = _validate_reason(reason)
    key = _validate_idempotency_key(idempotency_key)
    reference = str(reference or "").strip()
    if not reference or len(reference) > 240:
        raise BiometricGovernanceError("referencia_invalida", "Referencia obrigatoria.", 400)
    cursor.execute(
        """SELECT biometria_id,operacao,estado_resultante FROM operacoes_biometricas
           WHERE empresa_id=%s AND chave_idempotencia=%s""", (company_id, key)
    )
    prior = cursor.fetchone()
    if prior:
        if prior["operacao"] != operation:
            raise BiometricGovernanceError("idempotencia_conflitante", "Chave de idempotencia indisponivel.", 409)
        return {"biometria_id": str(prior["biometria_id"]), "hold": prior["estado_resultante"] == "hold_ativo", "reutilizada": True}
    cursor.execute(
        """SELECT id,status FROM biometrias WHERE empresa_id=%s AND funcionario_id=%s
           ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE""", (company_id, employee_id)
    )
    biometric = cursor.fetchone()
    if not biometric:
        raise BiometricGovernanceError("biometria_nao_encontrada", "Funcionario nao encontrado.", 404)
    cursor.execute(
        """SELECT id,versao FROM holds_biometricos WHERE empresa_id=%s AND biometria_id=%s
           AND cancelado_at IS NULL ORDER BY versao DESC LIMIT 1 FOR UPDATE""",
        (company_id, biometric["id"]),
    )
    active = cursor.fetchone()
    if operation == "criar_hold":
        if active:
            state = "hold_ativo"
        else:
            cursor.execute(
                """SELECT COALESCE(max(versao),0)+1 AS versao FROM holds_biometricos
                   WHERE empresa_id=%s AND biometria_id=%s""", (company_id, biometric["id"])
            )
            version = cursor.fetchone()["versao"]
            cursor.execute(
                """INSERT INTO holds_biometricos
                   (empresa_id,biometria_id,versao,justificativa,referencia,
                    criado_por_usuario_id,created_at,expira_at)
                   VALUES (%s,%s,%s,%s,%s,%s,clock_timestamp(),%s)""",
                (company_id, biometric["id"], version, reason, reference, actor_id, expires_at),
            )
            state = "hold_ativo"
    else:
        if active:
            cursor.execute(
                """UPDATE holds_biometricos SET cancelado_at=clock_timestamp(),
                   cancelado_por_usuario_id=%s,motivo_cancelamento=%s
                   WHERE empresa_id=%s AND id=%s""",
                (actor_id, reason, company_id, active["id"]),
            )
        state = "hold_cancelado"
    cursor.execute(
        """INSERT INTO operacoes_biometricas
           (empresa_id,biometria_id,funcionario_id,chave_idempotencia,operacao,
            motivo_codigo,ator_usuario_id,estado_resultante)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (company_id, biometric["id"], employee_id, key, operation, reason, actor_id, state),
    )
    _audit(cursor, company_id, actor_id, f"biometria.{operation}", biometric["id"],
           {"motivo_codigo": reason, "estado_novo": state})
    return {"biometria_id": str(biometric["id"]), "hold": state == "hold_ativo", "reutilizada": False}


def change_employee_status(
    cursor, *, company_id, employee_id, actor_id, target_status,
    away_policy: str,
):
    """Altera vinculo, biometria e sessoes na mesma transacao do chamador."""
    if target_status not in {"ativo", "afastado", "desligado"}:
        raise BiometricGovernanceError("status_vinculo_invalido", "Status invalido.", 400)
    if away_policy not in {"bloquear", "revogar", "preservar"}:
        raise BiometricGovernanceError(
            "politica_afastamento_invalida", "Politica de afastamento invalida.", 503
        )
    cursor.execute(
        """SELECT id,usuario_id,status FROM funcionarios
           WHERE empresa_id=%s AND id=%s FOR UPDATE""",
        (company_id, employee_id),
    )
    employee = cursor.fetchone()
    if not employee:
        raise BiometricGovernanceError("funcionario_nao_encontrado", "Funcionario nao encontrado.", 404)
    previous = employee["status"]
    if previous == target_status:
        return {"status": target_status, "reutilizada": True}
    governance = None
    if target_status == "desligado":
        governance = resolve_governance(cursor, company_id, lock=True)
    cursor.execute(
        "UPDATE funcionarios SET status=%s,updated_at=clock_timestamp() WHERE empresa_id=%s AND id=%s",
        (target_status, company_id, employee_id),
    )
    if target_status in {"desligado", "afastado"}:
        action = "revogar" if target_status == "desligado" else away_policy
        if action != "preservar":
            target = "revogada" if action == "revogar" else "bloqueada"
            cursor.execute(
                """SELECT id,status,politica_biometrica_id,perfil_tecnico_id
                   FROM biometrias WHERE empresa_id=%s AND funcionario_id=%s
                   AND status IN ('ativa','bloqueada') FOR UPDATE""",
                (company_id, employee_id),
            )
            for biometric in cursor.fetchall():
                assignments = ["status=%s", "motivo_codigo=%s", "updated_at=clock_timestamp()"]
                parameters = [target, f"vinculo_{target_status}"]
                if target == "revogada":
                    assignments.extend([
                        "revoked_at=clock_timestamp()",
                        "eliminacao_elegivel_at=clock_timestamp() + (%s * interval '1 day')",
                    ])
                    parameters.append(governance.retention_days)
                else:
                    assignments.append("bloqueada_at=clock_timestamp()")
                parameters.extend([company_id, biometric["id"]])
                cursor.execute(
                    f"UPDATE biometrias SET {', '.join(assignments)} WHERE empresa_id=%s AND id=%s",
                    tuple(parameters),
                )
                record_lifecycle(
                    cursor, company_id=company_id, employee_id=employee_id,
                    biometric_id=biometric["id"], actor_id=actor_id,
                    action=f"vinculo_{target_status}", previous=biometric["status"],
                    target=target, reason=f"vinculo_{target_status}",
                    policy_id=biometric["politica_biometrica_id"],
                    profile_id=biometric["perfil_tecnico_id"],
                )
        cursor.execute(
            """UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at,clock_timestamp())
               WHERE empresa_id=%s AND funcionario_id=%s AND revoked_at IS NULL""",
            (company_id, employee_id),
        )
    _audit(
        cursor, company_id, actor_id, "vinculo.status_alterado", employee_id,
        {"estado_anterior": previous, "estado_novo": target_status,
         "motivo_codigo": f"vinculo_{target_status}"},
    )
    return {"status": target_status, "reutilizada": False,
            "usuario_id": str(employee["usuario_id"])}


def governance_readiness(cursor, company_id: str) -> dict[str, bool]:
    try:
        resolve_governance(cursor, company_id)
    except BiometricGovernanceError:
        return {"policy": False, "profile": False, "compatible": False}
    return {"policy": True, "profile": True, "compatible": True}


def create_approved_policy(cursor, *, company_id, actor_id, payload):
    required = {
        "versao", "referencia_base_legal", "versao_aviso", "referencia_documental",
        "canal_atendimento", "retencao_dias", "vigencia_inicio",
    }
    if set(payload) != required:
        raise BiometricGovernanceError("politica_invalida", "Campos da politica invalidos.", 400)
    cursor.execute(
        """INSERT INTO politicas_biometricas
           (empresa_id,finalidade,versao,referencia_base_legal,versao_aviso,
            referencia_documental,canal_atendimento,retencao_dias,estado,
            vigencia_inicio,aprovado_por_usuario_id,aprovado_at)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'aprovada',%s,%s,clock_timestamp())
           RETURNING id,versao,versao_aviso,finalidade,retencao_dias""",
        (company_id, PURPOSE, payload["versao"], payload["referencia_base_legal"],
         payload["versao_aviso"], payload["referencia_documental"],
         payload["canal_atendimento"], payload["retencao_dias"],
         payload["vigencia_inicio"], actor_id),
    )
    row = cursor.fetchone()
    _audit(cursor, company_id, actor_id, "biometria.politica_aprovada", row["id"],
           {"versao": row["versao"], "versao_aviso": row["versao_aviso"],
            "finalidade": row["finalidade"], "retencao_dias": row["retencao_dias"]})
    return row


def create_active_profile(cursor, *, company_id, actor_id, payload):
    required = {"versao", "modelo", "versao_modelo", "dimensao", "metrica", "limiar", "versao_liveness", "vigencia_inicio", "referencia_relatorio"}
    if set(payload) != required:
        raise BiometricGovernanceError("perfil_invalido", "Campos do perfil invalidos.", 400)
    threshold = float(payload["limiar"])
    if not math.isfinite(threshold) or not 0 < threshold <= 2:
        raise BiometricGovernanceError("perfil_invalido", "Limiar invalido.", 400)
    # O relatório é apenas referência controlada; nunca recebe amostras/scores.
    report_reference = str(payload["referencia_relatorio"] or "").strip()
    if not report_reference or len(report_reference) > 240:
        raise BiometricGovernanceError("perfil_invalido", "Referencia de relatorio obrigatoria.", 400)
    cursor.execute(
        """INSERT INTO perfis_tecnicos_biometricos
           (empresa_id,finalidade,versao,modelo,versao_modelo,dimensao,metrica,
            limiar,versao_liveness,referencia_relatorio,estado,vigencia_inicio,aprovado_por_usuario_id,aprovado_at)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ativo',%s,%s,clock_timestamp())
           RETURNING id,versao,modelo,versao_modelo,dimensao,metrica,limiar,versao_liveness""",
        (company_id, PURPOSE, payload["versao"], payload["modelo"],
         payload["versao_modelo"], payload["dimensao"], payload["metrica"],
         threshold, payload["versao_liveness"], report_reference,
         payload["vigencia_inicio"], actor_id),
    )
    row = cursor.fetchone()
    _audit(cursor, company_id, actor_id, "biometria.perfil_ativado", row["id"],
           {"versao": row["versao"], "modelo": row["modelo"],
            "versao_modelo": row["versao_modelo"], "dimensao": row["dimensao"],
            "metrica": row["metrica"], "limiar": row["limiar"],
            "versao_liveness": row["versao_liveness"],
            "referencia_relatorio": report_reference})
    return row


def purge_eligible(connection, *, company_id: str, execute: bool = False, limit: int = 100):
    """Elimina material vencido; dry-run e o comportamento padrao."""
    if not 1 <= int(limit) <= 500:
        raise ValueError("limit deve estar entre 1 e 500")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT b.id,b.funcionario_id,b.status,b.politica_biometrica_id,b.perfil_tecnico_id
            FROM biometrias b
            WHERE b.empresa_id=%s AND b.status='exclusao_pendente'
              AND b.eliminacao_elegivel_at <= clock_timestamp()
              AND NOT EXISTS (
                SELECT 1 FROM holds_biometricos h
                WHERE h.empresa_id=b.empresa_id AND h.biometria_id=b.id
                  AND h.cancelado_at IS NULL
                  AND (h.expira_at IS NULL OR h.expira_at > clock_timestamp())
              )
            ORDER BY b.eliminacao_elegivel_at,b.id
            LIMIT %s
            FOR UPDATE OF b SKIP LOCKED
            """,
            (company_id, int(limit)),
        )
        rows = cursor.fetchall()
        if not execute:
            connection.rollback()
            return {"dry_run": True, "elegiveis": len(rows), "eliminadas": 0}
        for row in rows:
            cursor.execute(
                """UPDATE biometrias SET embedding=NULL,referencia_arquivo_privado=NULL,
                   status='eliminada',eliminada_at=clock_timestamp(),updated_at=clock_timestamp(),
                   motivo_codigo='retencao_vencida'
                   WHERE empresa_id=%s AND id=%s AND status='exclusao_pendente'""",
                (company_id, row["id"]),
            )
            if cursor.rowcount:
                record_lifecycle(
                    cursor, company_id=company_id, employee_id=row["funcionario_id"],
                    biometric_id=row["id"], actor_id=None, action="eliminar",
                    previous=row["status"], target="eliminada",
                    reason="retencao_vencida", policy_id=row["politica_biometrica_id"],
                    profile_id=row["perfil_tecnico_id"],
                )
        connection.commit()
        return {"dry_run": False, "elegiveis": len(rows), "eliminadas": len(rows)}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
