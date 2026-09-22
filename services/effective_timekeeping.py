"""Visão lógica e imutável de marcações com correções aprovadas."""


def fetch_effective_events(cursor, company_id, employee_id, start_utc=None, end_utc=None):
    cursor.execute(
        """
        WITH eventos_originais AS (
            SELECT
                m.id::text AS id,
                m.id AS marcacao_original_id,
                COALESCE(ci.instante_proposto, m.instante) AS instante,
                COALESCE(ct.tipo_marcacao_proposto, m.tipo) AS tipo,
                m.origem,
                (ci.id IS NOT NULL OR ct.id IS NOT NULL) AS ajustada,
                COALESCE(ci.id, ct.id) AS correcao_id
            FROM marcacoes m
            LEFT JOIN correcoes ci
              ON ci.empresa_id = m.empresa_id
             AND ci.funcionario_id = m.funcionario_id
             AND ci.marcacao_original_id = m.id
             AND ci.tipo = 'alteracao_instante'
             AND ci.estado = 'aprovada'
            LEFT JOIN correcoes ct
              ON ct.empresa_id = m.empresa_id
             AND ct.funcionario_id = m.funcionario_id
             AND ct.marcacao_original_id = m.id
             AND ct.tipo = 'alteracao_tipo'
             AND ct.estado = 'aprovada'
            WHERE m.empresa_id = %s
              AND m.funcionario_id = %s
              AND m.estado = 'confirmada'
        ), eventos_incluidos AS (
            SELECT
                ('ajuste:' || c.id::text) AS id,
                NULL::uuid AS marcacao_original_id,
                c.instante_proposto AS instante,
                c.tipo_marcacao_proposto AS tipo,
                'ajuste_administrativo'::text AS origem,
                TRUE AS ajustada,
                c.id AS correcao_id
            FROM correcoes c
            WHERE c.empresa_id = %s
              AND c.funcionario_id = %s
              AND c.tipo = 'inclusao'
              AND c.estado = 'aprovada'
        )
        SELECT *
        FROM (
            SELECT * FROM eventos_originais
            UNION ALL
            SELECT * FROM eventos_incluidos
        ) eventos
        WHERE (%s::timestamptz IS NULL OR instante >= %s)
          AND (%s::timestamptz IS NULL OR instante < %s)
        ORDER BY instante ASC, id ASC
        """,
        (
            company_id, employee_id, company_id, employee_id,
            start_utc, start_utc, end_utc, end_utc,
        ),
    )
    return cursor.fetchall()
