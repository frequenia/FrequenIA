"""Workflow transacional das correcoes de ponto Gestor -> RH.

As rotas apenas traduzem HTTP. Autorizacao, transicoes, lock, auditoria e
efeitos colaterais da decisao ficam centralizados aqui.
"""

import psycopg2.extras

from services.management_scope import employee_scope_clause


PENDING_MANAGER = "pendente_gestor"
FORWARDED_HR = "encaminhada_rh"
FINAL_STATES = {"aprovada", "rejeitada", "cancelada"}
MAX_JUSTIFICATION_LENGTH = 1000


class CorrectionWorkflowError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_justification(value, required=False):
    normalized = " ".join(str(value or "").split())
    if required and not normalized:
        raise CorrectionWorkflowError("Observação é obrigatória para esta transição.", 400)
    if len(normalized) > MAX_JUSTIFICATION_LENGTH:
        raise CorrectionWorkflowError(
            f"Observação deve ter no máximo {MAX_JUSTIFICATION_LENGTH} caracteres.",
            400,
        )
    return normalized or None


def allowed_actions(role, state, own=False):
    if own:
        return ["cancelar"] if state == PENDING_MANAGER else []
    if role == "gestor" and state == PENDING_MANAGER:
        return ["aprovar", "rejeitar", "encaminhar-rh"]
    if role in {"rh", "administrador"} and state == FORWARDED_HR:
        return ["aprovar", "rejeitar"]
    return []


def _locked_correction(cursor, auth_context, correction_id, own):
    conditions = ["c.id = %s", "c.empresa_id = %s"]
    params = [correction_id, auth_context["empresa_id"]]
    if own:
        conditions += ["c.funcionario_id = %s", "c.solicitante_usuario_id = %s"]
        params += [auth_context["funcionario_id"], auth_context["user_id"]]
        scope = "TRUE"
        scope_params = ()
    else:
        scope, scope_params = employee_scope_clause(auth_context, "f")
    params.extend(scope_params)
    cursor.execute(
        """SELECT c.* FROM correcoes c
           INNER JOIN funcionarios f
             ON f.id = c.funcionario_id AND f.empresa_id = c.empresa_id
           WHERE """
        + " AND ".join(conditions)
        + " AND (" + scope + ") FOR UPDATE OF c",
        tuple(params),
    )
    return cursor.fetchone()


def _validate_shape(cursor, auth_context, row):
    valid = {
        "inclusao": (
            not row.get("marcacao_original_id")
            and row.get("instante_proposto")
            and row.get("tipo_marcacao_proposto")
        ),
        "alteracao_instante": row.get("marcacao_original_id") and row.get("instante_proposto"),
        "alteracao_tipo": row.get("marcacao_original_id") and row.get("tipo_marcacao_proposto"),
        "justificativa": True,
    }.get(row.get("tipo"), False)
    if not valid:
        raise CorrectionWorkflowError("A solicitação não possui dados válidos para aprovação.")
    if row.get("marcacao_original_id"):
        cursor.execute(
            """SELECT id FROM marcacoes
               WHERE id = %s AND empresa_id = %s AND funcionario_id = %s
                 AND estado = 'confirmada' FOR UPDATE""",
            (
                row["marcacao_original_id"],
                auth_context["empresa_id"],
                row["funcionario_id"],
            ),
        )
        if not cursor.fetchone():
            raise CorrectionWorkflowError("Marcação original não encontrada.")


def _audit(cursor, auth_context, row, previous, target, justification):
    action = {
        "encaminhada_rh": "correcao.encaminhada_rh",
        "aprovada": "correcao.aprovada",
        "rejeitada": "correcao.rejeitada",
        "cancelada": "correcao.cancelada",
    }[target]
    metadata = {
        "correcao_id": str(row["id"]),
        "estado_anterior": previous,
        "estado_novo": target,
        "papel": auth_context["perfil"],
        "justificativa": justification,
        "empresa_id": str(auth_context["empresa_id"]),
        "funcionario_id": str(row["funcionario_id"]),
        "acao": action,
    }
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id, ator_usuario_id, acao, entidade_tipo, entidade_id, metadados)
           VALUES (%s, %s, %s, 'correcao', %s, %s)""",
        (
            auth_context["empresa_id"],
            auth_context["user_id"],
            action,
            row["id"],
            psycopg2.extras.Json(metadata),
        ),
    )


def _notify(cursor, auth_context, user_id, target):
    messages = {
        "encaminhada_rh": (
            "Correção encaminhada ao RH",
            "Sua solicitação de correção de ponto foi encaminhada ao RH.",
        ),
        "aprovada": (
            "Correção de ponto aprovada",
            "Sua solicitação de correção de ponto foi aprovada.",
        ),
        "rejeitada": (
            "Correção de ponto rejeitada",
            "Sua solicitação de correção de ponto foi rejeitada.",
        ),
    }
    if target not in messages:
        return
    title, message = messages[target]
    cursor.execute(
        """INSERT INTO notificacoes (empresa_id, usuario_id, tipo, titulo, mensagem)
           VALUES (%s, %s, 'correcao', %s, %s)""",
        (auth_context["empresa_id"], user_id, title, message),
    )


def transition_correction(
    connection_factory, auth_context, correction_id, target, justification=None, own=False
):
    """Aplica uma unica transicao sob lock e revalida o estado na transacao."""
    required = target in {"rejeitada", FORWARDED_HR}
    justification = normalize_justification(justification, required=required)
    action_name = {
        "aprovada": "aprovar",
        "rejeitada": "rejeitar",
        FORWARDED_HR: "encaminhar-rh",
        "cancelada": "cancelar",
    }.get(target)
    if not action_name:
        raise CorrectionWorkflowError("Transição inválida.", 400)

    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        row = _locked_correction(cursor, auth_context, correction_id, own)
        if not row:
            raise CorrectionWorkflowError("Ocorrência não encontrada.", 404)
        if action_name not in allowed_actions(auth_context["perfil"], row["estado"], own):
            if row["estado"] in FINAL_STATES:
                message = "A ocorrência já está em estado final."
            else:
                message = "Transição não permitida para o estado e papel atuais."
            raise CorrectionWorkflowError(message)
        if target == "aprovada":
            _validate_shape(cursor, auth_context, row)

        if target in FINAL_STATES:
            cursor.execute(
                """UPDATE correcoes
                   SET estado = %s, responsavel_decisao_usuario_id = %s,
                       decisao = %s, decided_at = clock_timestamp(),
                       updated_at = clock_timestamp()
                   WHERE id = %s RETURNING *""",
                (target, auth_context["user_id"], justification, row["id"]),
            )
        else:
            cursor.execute(
                """UPDATE correcoes
                   SET estado = %s, responsavel_decisao_usuario_id = %s,
                       decisao = %s, decided_at = NULL,
                       updated_at = clock_timestamp()
                   WHERE id = %s RETURNING *""",
                (target, auth_context["user_id"], justification, row["id"]),
            )
        updated = cursor.fetchone()

        if row.get("ocorrencia_id"):
            if target == "cancelada":
                cursor.execute(
                    """UPDATE ocorrencias SET estado = 'arquivada',
                       updated_at = clock_timestamp() WHERE id = %s""",
                    (row["ocorrencia_id"],),
                )
            elif target == FORWARDED_HR:
                cursor.execute(
                    """UPDATE ocorrencias SET estado = 'em_analise',
                       responsavel_usuario_id = %s, decisao = %s,
                       updated_at = clock_timestamp() WHERE id = %s""",
                    (auth_context["user_id"], target, row["ocorrencia_id"]),
                )
            else:
                cursor.execute(
                    """UPDATE ocorrencias SET estado = 'resolvida',
                       responsavel_usuario_id = %s, decisao = %s,
                       resolved_at = clock_timestamp(), updated_at = clock_timestamp()
                       WHERE id = %s""",
                    (auth_context["user_id"], target, row["ocorrencia_id"]),
                )

        _audit(cursor, auth_context, row, row["estado"], target, justification)
        _notify(cursor, auth_context, row["solicitante_usuario_id"], target)
        connection.commit()
        return updated
    except CorrectionWorkflowError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        if getattr(exc, "pgcode", None) == "23505":
            raise CorrectionWorkflowError(
                "Já existe correção aprovada para esta marcação."
            ) from exc
        raise
    finally:
        cursor.close()
        connection.close()
