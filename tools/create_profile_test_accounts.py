"""Cria contas sintéticas de homologação para todos os perfis do sistema."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2.extras
from werkzeug.security import generate_password_hash

from db import conectar_bd
from services.employee_onboarding import allocate_registration


COMPANY_CNPJ = "99000000000101"
COMPANY_NAME = "FrequenIA Homologação de Perfis"


def synthetic_cpf(base):
    digits = [int(value) for value in f"{base:09d}"]
    for weight_start in (10, 11):
        total = sum(value * (weight_start - index) for index, value in enumerate(digits))
        remainder = total % 11
        digits.append(0 if remainder < 2 else 11 - remainder)
    return "".join(str(value) for value in digits)


def upsert_named(cursor, table, company_id, name, extra=None):
    extra = extra or {}
    columns = ["empresa_id", "nome", *extra]
    values = [company_id, name, *extra.values()]
    placeholders = ", ".join(["%s"] * len(values))
    cursor.execute(
        f"""INSERT INTO {table} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (empresa_id, nome) DO UPDATE SET nome = EXCLUDED.nome
            RETURNING id""",
        tuple(values),
    )
    return cursor.fetchone()["id"]


def main():
    accounts = [
        ("administrador_geral", "Administrador Geral de Teste", synthetic_cpf(920000001), "AdminGeral@2026"),
        ("administrador", "Gestor de RH de Teste", synthetic_cpf(920000002), "GestorRH@2026"),
        ("rh", "RH de Teste", synthetic_cpf(920000003), "RHTeste@2026"),
        ("gestor", "Gestor de Equipe de Teste", synthetic_cpf(920000004), "GestorTeste@2026"),
        ("funcionario", "Funcionário de Teste", synthetic_cpf(920000005), "Funcionario@2026"),
    ]
    result = []
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """INSERT INTO empresas (nome, cnpj, status)
                   VALUES (%s, %s, 'ativa')
                   ON CONFLICT (cnpj) DO UPDATE SET nome = EXCLUDED.nome, status = 'ativa'
                   RETURNING id""",
                (COMPANY_NAME, COMPANY_CNPJ),
            )
            company_id = cursor.fetchone()["id"]
            unit_id = upsert_named(cursor, "unidades", company_id, "Matriz Homologação")
            cursor.execute(
                """INSERT INTO equipes (empresa_id, unidade_id, nome, status)
                   VALUES (%s, %s, 'Equipe Homologação', 'ativa')
                   ON CONFLICT (unidade_id, nome) DO UPDATE SET status = 'ativa'
                   RETURNING id""",
                (company_id, unit_id),
            )
            team_id = cursor.fetchone()["id"]

            role_ids = {}
            for profile, role_name in {
                "administrador": "Administração de RH",
                "rh": "Recursos Humanos",
                "gestor": "Gestão de Equipe",
                "funcionario": "Operação",
            }.items():
                role_ids[profile] = upsert_named(cursor, "cargos", company_id, role_name)

            for profile, name, cpf, password in accounts:
                email = f"teste.perfil.{profile}@example.invalid"
                system_profile = "administrador_geral" if profile == "administrador_geral" else None
                cursor.execute("SELECT id FROM usuarios WHERE cpf = %s", (cpf,))
                user = cursor.fetchone()
                if user:
                    user_id = user["id"]
                    cursor.execute(
                        """UPDATE usuarios
                           SET nome=%s, email=%s, senha_hash=%s, status='ativo',
                               perfil_sistema=%s, primeiro_acesso_pendente=false,
                               updated_at=now()
                           WHERE id=%s""",
                        (name, email, generate_password_hash(password), system_profile, user_id),
                    )
                else:
                    cursor.execute(
                        """INSERT INTO usuarios (
                               nome, cpf, email, senha_hash, status,
                               perfil_sistema, primeiro_acesso_pendente
                           ) VALUES (%s,%s,%s,%s,'ativo',%s,false)
                           RETURNING id""",
                        (name, cpf, email, generate_password_hash(password), system_profile),
                    )
                    user_id = cursor.fetchone()["id"]

                cursor.execute(
                    "UPDATE auth_sessions SET revoked_at=COALESCE(revoked_at, now()) WHERE usuario_id=%s",
                    (user_id,),
                )
                cursor.execute(
                    """UPDATE password_reset_tokens SET revoked_at=COALESCE(revoked_at, now())
                       WHERE usuario_id=%s AND used_at IS NULL""",
                    (user_id,),
                )

                registration = None
                if profile != "administrador_geral":
                    cursor.execute(
                        "SELECT id, matricula FROM funcionarios WHERE empresa_id=%s AND usuario_id=%s",
                        (company_id, user_id),
                    )
                    employee = cursor.fetchone()
                    if employee:
                        employee_id = employee["id"]
                        registration = employee["matricula"]
                        cursor.execute(
                            """UPDATE funcionarios SET unidade_id=%s, equipe_id=%s, cargo_id=%s,
                                      perfil=%s, status='ativo', updated_at=now()
                               WHERE id=%s""",
                            (unit_id, team_id, role_ids[profile], profile, employee_id),
                        )
                    else:
                        registration = allocate_registration(
                            cursor, company_id, role_ids[profile]
                        )
                        cursor.execute(
                            """INSERT INTO funcionarios (
                                   usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                                   matricula, data_admissao, tipo_contrato,
                                   carga_horaria_semanal, perfil, status
                               ) VALUES (%s,%s,%s,%s,%s,%s,current_date,'efetivo',40,%s,'ativo')
                               RETURNING id""",
                            (
                                user_id,
                                company_id,
                                unit_id,
                                team_id,
                                role_ids[profile],
                                registration,
                                profile,
                            ),
                        )
                        employee_id = cursor.fetchone()["id"]

                    if profile == "gestor":
                        cursor.execute(
                            """INSERT INTO gestores_escopos (
                                   empresa_id, gestor_funcionario_id, unidade_id, equipe_id
                               ) SELECT %s,%s,%s,%s
                               WHERE NOT EXISTS (
                                   SELECT 1 FROM gestores_escopos
                                   WHERE empresa_id=%s AND gestor_funcionario_id=%s
                                     AND unidade_id=%s AND equipe_id=%s
                               )""",
                            (
                                company_id,
                                employee_id,
                                unit_id,
                                team_id,
                                company_id,
                                employee_id,
                                unit_id,
                                team_id,
                            ),
                        )

                result.append(
                    {
                        "perfil": profile,
                        "cpf": cpf,
                        "senha": password,
                        "matricula": registration,
                    }
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(json.dumps({"empresa": COMPANY_NAME, "contas": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
