"""Regra central de visibilidade de funcionários para APIs de gestão.

O tenant vem sempre do contexto autenticado.  Administrador e RH continuam
com o escopo inteiro da empresa; gestor precisa de uma atribuição explícita em
``gestores_escopos`` para uma unidade inteira ou uma equipe daquela unidade.
"""


def employee_scope_clause(auth_context, employee_alias="f"):
    """Retorna predicado SQL e parâmetros para o funcionário visível.

    O alias é interno e fixo nas consultas que usam este helper; ele não recebe
    dados do cliente.  A empresa continua sendo filtrada pelas rotas, para que
    a política mantenha as responsabilidades separadas e seja reutilizável.
    """
    if auth_context["perfil"] != "gestor":
        return "TRUE", ()

    return (
        f"""EXISTS (
            SELECT 1
            FROM gestores_escopos ge
            WHERE ge.empresa_id = {employee_alias}.empresa_id
              AND ge.gestor_funcionario_id = %s
              AND ge.unidade_id = {employee_alias}.unidade_id
              AND (ge.equipe_id IS NULL OR ge.equipe_id = {employee_alias}.equipe_id)
        )""",
        (auth_context["funcionario_id"],),
    )


def employee_visibility_query(auth_context, employee_id, employee_alias="f"):
    """Consulta parametrizada para validar um funcionário sem enumerá-lo."""
    clause, scope_params = employee_scope_clause(auth_context, employee_alias)
    return (
        f"SELECT 1 FROM funcionarios {employee_alias} "
        f"WHERE {employee_alias}.id = %s "
        f"AND {employee_alias}.empresa_id = %s AND ({clause})",
        (employee_id, auth_context["empresa_id"], *scope_params),
    )
