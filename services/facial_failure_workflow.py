"""Workflow transacional de ocorrências automáticas de falha facial."""

from uuid import UUID

import psycopg2.extras

from db import conectar_bd
from services.management_scope import employee_scope_clause


TRANSITIONS = {
    "aberta": frozenset({"em_analise", "resolvida", "descartada"}),
    "em_analise": frozenset({"resolvida", "descartada"}),
    "resolvida": frozenset(),
    "descartada": frozenset(),
}
FINAL_STATES = frozenset({"resolvida", "descartada"})


class FacialFailureWorkflowError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FacialFailureWorkflowError("Ocorrência inválida.", 400) from exc


def _justification(value, required):
    text = str(value or "").strip()
    if required and not text:
        raise FacialFailureWorkflowError(
            "Justificativa é obrigatória para concluir a ocorrência.", 400
        )
    if len(text) > 2000:
        raise FacialFailureWorkflowError("Justificativa excede 2000 caracteres.", 400)
    return text or None


def transition_facial_failure_occurrence(auth_context, occurrence_id, target, justification=None):
    """Aplica uma transição sob lock e registra auditoria na mesma transação."""
    if target not in {"em_analise", *FINAL_STATES}:
        raise FacialFailureWorkflowError("Transição inválida.", 400)
    identifier = _uuid(occurrence_id)
    decision = _justification(justification, target in FINAL_STATES)
    connection = conectar_bd()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        scope_clause, scope_params = employee_scope_clause(auth_context, "f")
        cursor.execute(
            """SELECT o.id, o.estado
               FROM ocorrencias o
               INNER JOIN funcionarios f
                 ON f.id = o.funcionario_id AND f.empresa_id = o.empresa_id
               WHERE o.id = %s AND o.empresa_id = %s
                 AND o.tipo = 'falha_facial'
                 AND o.ciclo_falha_facial_id IS NOT NULL
                 AND (""" + scope_clause + ") FOR UPDATE OF o",
            (identifier, auth_context["empresa_id"], *scope_params),
        )
        current = cursor.fetchone()
        if not current:
            raise FacialFailureWorkflowError("Ocorrência não encontrada.", 404)
        current_state = current["estado"]
        if target not in TRANSITIONS.get(current_state, frozenset()):
            raise FacialFailureWorkflowError(
                "A ocorrência foi alterada ou não permite esta transição.", 409
            )

        if target in FINAL_STATES:
            cursor.execute(
                """UPDATE ocorrencias
                   SET estado = %s, responsavel_usuario_id = %s, decisao = %s,
                       resolved_at = clock_timestamp(), updated_at = clock_timestamp()
                   WHERE id = %s
                   RETURNING id, estado, responsavel_usuario_id, decisao,
                             resolved_at, updated_at""",
                (target, auth_context["user_id"], decision, identifier),
            )
        else:
            cursor.execute(
                """UPDATE ocorrencias
                   SET estado = 'em_analise', responsavel_usuario_id = %s,
                       updated_at = clock_timestamp()
                   WHERE id = %s
                   RETURNING id, estado, responsavel_usuario_id, decisao,
                             resolved_at, updated_at""",
                (auth_context["user_id"], identifier),
            )
        updated = cursor.fetchone()
        metadata = {"estado_anterior": current_state, "estado_novo": target}
        if decision:
            metadata["justificativa"] = decision
        cursor.execute(
            """INSERT INTO auditoria
               (empresa_id, ator_usuario_id, acao, entidade_tipo, entidade_id, metadados)
               VALUES (%s, %s, %s, 'ocorrencia', %s, %s)""",
            (
                auth_context["empresa_id"],
                auth_context["user_id"],
                f"ocorrencia.falha_facial.{target}",
                identifier,
                psycopg2.extras.Json(metadata),
            ),
        )
        connection.commit()
        return updated
    except FacialFailureWorkflowError:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
