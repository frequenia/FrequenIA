"""Cadastro transacional de empresa e de seu primeiro administrador."""

import psycopg2.extras

from services.employee_onboarding import allocate_registration


DEFAULT_UNIT_NAME = "Matriz"
DEFAULT_UNIT_CODE = "MATRIZ"
DEFAULT_TEAM_NAME = "Administração/RH"
DEFAULT_ROLE_NAME = "Gestor de RH"
DEFAULT_ROLE_REGISTRATION_CODE = "GDRH"


class CompanyOnboardingConflict(ValueError):
    """Indica conflito de unicidade conhecido antes da escrita."""


def create_company_with_initial_admin(
    cursor,
    *,
    company_name,
    cnpj,
    administrator,
    credentials,
    actor_user_id,
    invitation_minutes,
):
    """Cria todo o onboarding inicial dentro da transação do chamador."""
    cursor.execute("SELECT 1 FROM empresas WHERE cnpj = %s", (cnpj,))
    if cursor.fetchone():
        raise CompanyOnboardingConflict("CNPJ já cadastrado.")

    cursor.execute(
        "SELECT cpf, email FROM usuarios WHERE cpf = %s OR email = %s",
        (administrator["cpf"], administrator["email"]),
    )
    duplicate = cursor.fetchone()
    if duplicate:
        if duplicate.get("cpf") == administrator["cpf"]:
            raise CompanyOnboardingConflict("CPF do administrador já cadastrado.")
        raise CompanyOnboardingConflict("E-mail do administrador já cadastrado.")

    cursor.execute(
        """INSERT INTO empresas (cnpj, nome, status)
           VALUES (%s, %s, 'ativa')
           RETURNING id, cnpj, nome, status, created_at""",
        (cnpj, company_name),
    )
    company = cursor.fetchone()

    cursor.execute(
        """INSERT INTO unidades (empresa_id, nome, codigo, timezone, status)
           VALUES (%s, %s, %s, 'America/Sao_Paulo', 'ativa')
           RETURNING id, nome, codigo""",
        (company["id"], DEFAULT_UNIT_NAME, DEFAULT_UNIT_CODE),
    )
    unit = cursor.fetchone()

    cursor.execute(
        """INSERT INTO equipes (empresa_id, unidade_id, nome, status)
           VALUES (%s, %s, %s, 'ativa')
           RETURNING id, nome""",
        (company["id"], unit["id"], DEFAULT_TEAM_NAME),
    )
    team = cursor.fetchone()

    cursor.execute(
        """INSERT INTO cargos (
               empresa_id, nome, codigo_matricula, status
           ) VALUES (%s, %s, %s, 'ativo')
           RETURNING id, nome, codigo_matricula""",
        (
            company["id"],
            DEFAULT_ROLE_NAME,
            DEFAULT_ROLE_REGISTRATION_CODE,
        ),
    )
    role = cursor.fetchone()
    registration = allocate_registration(cursor, company["id"], role["id"])

    cursor.execute(
        """INSERT INTO usuarios (
               nome, cpf, email, telefone, senha_hash, status,
               primeiro_acesso_pendente
           ) VALUES (%s, %s, %s, %s, %s, 'bloqueado', true)
           RETURNING id, nome, email, status, primeiro_acesso_pendente""",
        (
            administrator["nome"],
            administrator["cpf"],
            administrator["email"],
            administrator["telefone"],
            credentials["password_hash"],
        ),
    )
    user = cursor.fetchone()

    cursor.execute(
        """INSERT INTO funcionarios (
               usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
               matricula, perfil, status
           ) VALUES (%s, %s, %s, %s, %s, %s, 'administrador', 'ativo')
           RETURNING id""",
        (
            user["id"],
            company["id"],
            unit["id"],
            team["id"],
            role["id"],
            registration,
        ),
    )
    employee = cursor.fetchone()

    cursor.execute(
        """INSERT INTO password_reset_tokens (
               usuario_id, token_hash, purpose, expires_at
           ) VALUES (%s, %s, 'first_access',
                     clock_timestamp() + (%s * interval '1 minute'))""",
        (user["id"], credentials["token_hash"], invitation_minutes),
    )

    audit_events = (
        (
            "empresa.criada",
            "empresa",
            company["id"],
            {"cnpj": cnpj, "nome": company_name},
        ),
        (
            "empresa.estrutura_inicial_criada",
            "empresa",
            company["id"],
            {
                "unidade_id": str(unit["id"]),
                "equipe_id": str(team["id"]),
                "cargo_id": str(role["id"]),
            },
        ),
        (
            "empresa.administrador_inicial_criado",
            "usuario",
            user["id"],
            {
                "funcionario_id": str(employee["id"]),
                "perfil": "administrador",
                "matricula": registration,
                "primeiro_acesso_pendente": True,
            },
        ),
    )
    for action, entity_type, entity_id, metadata in audit_events:
        cursor.execute(
            """INSERT INTO auditoria (
                   empresa_id, ator_usuario_id, acao,
                   entidade_tipo, entidade_id, metadados
               ) VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                company["id"],
                actor_user_id,
                action,
                entity_type,
                entity_id,
                psycopg2.extras.Json(metadata),
            ),
        )

    administrator_response = dict(user)
    administrator_response.update(
        {
            "funcionario_id": employee["id"],
            "perfil": "administrador",
            "matricula": registration,
        }
    )
    return {
        "empresa": company,
        "administrador": administrator_response,
        "estrutura": {"unidade": unit, "equipe": team, "cargo": role},
    }
