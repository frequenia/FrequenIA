"""Cria o primeiro administrador geral e envia o convite de primeiro acesso."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from db import conectar_bd
from services.email_service import send_password_reset_email
from services.employee_onboarding import first_access_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", required=True)
    parser.add_argument("--cpf", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    cpf = re.sub(r"\D", "", args.cpf)
    email = args.email.strip().lower()
    nome = " ".join(args.nome.split())
    if len(cpf) != 11 or not nome or "@" not in email:
        raise SystemExit("Nome, CPF ou e-mail inválido.")

    credentials = first_access_credentials()
    connection = conectar_bd()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO usuarios (
                       nome, cpf, email, senha_hash, status,
                       perfil_sistema, primeiro_acesso_pendente
                   ) VALUES (%s, %s, %s, %s, 'bloqueado',
                             'administrador_geral', true)
                   RETURNING id""",
                (nome, cpf, email, credentials["password_hash"]),
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO password_reset_tokens (
                       usuario_id, token_hash, purpose, expires_at
                   ) VALUES (%s, %s, 'first_access',
                             now() + (%s * interval '1 minute'))""",
                (
                    user_id,
                    credentials["token_hash"],
                    app.config["PASSWORD_RESET_TOKEN_MINUTES"],
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    with app.app_context():
        send_password_reset_email(
            email,
            credentials["raw_token"],
            app.config["PASSWORD_RESET_TOKEN_MINUTES"],
        )
    print("Administrador geral criado; convite enviado.")


if __name__ == "__main__":
    main()
