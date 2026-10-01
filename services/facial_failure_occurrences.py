"""Domínio transacional para ocorrências automáticas de falha facial."""

import psycopg2.extras

COUNTED_FAILURE_REASONS = frozenset({"liveness_reprovado", "nao_corresponde"})
FAILURE_CYCLE_SIZE = 5


def _field(row, name, index):
    return row[name] if isinstance(row, dict) else row[index]


def consume_facial_failure_cycle(cursor, company_id, employee_id):
    """Consome as primeiras cinco falhas válidas pendentes, se existirem.

    O lock é por empresa+funcionário e inclui o mesmo namespace usado nas
    marcações. Isso torna retry, reprocessamento e quinta falha concorrente
    serializáveis. A ocorrência recebe o instante da primeira tentativa.
    """
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{company_id}:{employee_id}",),
    )
    cursor.execute(
        """SELECT id, instante
           FROM tentativas_faciais
           WHERE empresa_id = %s
             AND funcionario_id = %s
             AND ocorrencia_id IS NULL
             AND resultado = 'falha'
             AND motivo_codigo IN ('liveness_reprovado', 'nao_corresponde')
           ORDER BY instante ASC, id ASC
           LIMIT %s
           FOR UPDATE""",
        (company_id, employee_id, FAILURE_CYCLE_SIZE),
    )
    attempts = cursor.fetchall()
    if len(attempts) < FAILURE_CYCLE_SIZE:
        return None

    first_attempt = attempts[0]
    cursor.execute(
        """INSERT INTO ocorrencias
           (empresa_id, funcionario_id, tentativa_facial_id, tipo, descricao,
            estado, primeira_ocorrencia_at, ciclo_falha_facial_id)
           VALUES (%s, %s, %s, 'falha_facial',
                   'Ocorrência automática após cinco falhas faciais válidas.',
                   'aberta', %s, %s)
           RETURNING id, primeira_ocorrencia_at""",
        (
            company_id,
            employee_id,
            _field(first_attempt, "id", 0),
            _field(first_attempt, "instante", 1),
            _field(first_attempt, "id", 0),
        ),
    )
    occurrence = cursor.fetchone()
    occurrence_id = _field(occurrence, "id", 0)
    attempt_ids = [_field(attempt, "id", 0) for attempt in attempts]
    cursor.execute(
        """UPDATE tentativas_faciais
           SET ocorrencia_id = %s, consumida_at = clock_timestamp()
           WHERE empresa_id = %s
             AND funcionario_id = %s
             AND id = ANY(%s::uuid[])
             AND ocorrencia_id IS NULL""",
        (occurrence_id, company_id, employee_id, attempt_ids),
    )
    if cursor.rowcount != FAILURE_CYCLE_SIZE:
        raise RuntimeError("O ciclo de falhas faciais foi alterado concorrentemente.")
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id, ator_usuario_id, acao, entidade_tipo, entidade_id, metadados)
           VALUES (%s, NULL, 'ocorrencia.falha_facial_automatica', 'ocorrencia', %s,
                   %s)""",
        (
            company_id,
            occurrence_id,
            psycopg2.extras.Json({"quantidade_tentativas": FAILURE_CYCLE_SIZE}),
        ),
    )
    return occurrence
