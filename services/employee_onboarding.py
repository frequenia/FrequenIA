"""Primeiro acesso e matricula automatica de funcionarios."""

import hashlib
import re
import secrets
import unicodedata

from werkzeug.security import generate_password_hash


def cargo_registration_code(name):
    normalized = unicodedata.normalize("NFKD", str(name or ""))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").upper()
    words = re.findall(r"[A-Z0-9]+", ascii_name)
    significant_words = [
        word for word in words if word not in {"A", "AS", "O", "OS", "DE", "DA", "DAS", "DO", "DOS", "E"}
    ]
    code = "".join(word[0] for word in significant_words)[:6]
    return code or "CG"


def allocate_registration(cursor, company_id, role_id):
    """Reserva uma sequencia por empresa/cargo dentro da transacao atual."""
    cursor.execute(
        """SELECT nome, codigo_matricula FROM cargos
           WHERE id = %s AND empresa_id = %s AND status = 'ativo'
           FOR UPDATE""",
        (role_id, company_id),
    )
    role = cursor.fetchone()
    if not role:
        raise ValueError("Cargo inválido.")

    code = role.get("codigo_matricula")
    if not code:
        base = cargo_registration_code(role["nome"])
        code = base
        suffix = 2
        while True:
            cursor.execute(
                """SELECT 1 FROM cargos
                   WHERE empresa_id = %s AND codigo_matricula = %s AND id <> %s""",
                (company_id, code, role_id),
            )
            if not cursor.fetchone():
                break
            code = f"{base}{suffix}"
            suffix += 1
        cursor.execute(
            "UPDATE cargos SET codigo_matricula = %s, updated_at = now() WHERE id = %s",
            (code, role_id),
        )

    cursor.execute(
        """INSERT INTO matriculas_sequencias (empresa_id, cargo_id, ultimo_numero)
           VALUES (%s, %s, 1)
           ON CONFLICT (empresa_id, cargo_id) DO UPDATE
           SET ultimo_numero = matriculas_sequencias.ultimo_numero + 1,
               updated_at = now()
           RETURNING ultimo_numero""",
        (company_id, role_id),
    )
    sequence = cursor.fetchone()["ultimo_numero"]
    return f"{code}-{sequence:06d}"


def first_access_credentials():
    """Cria senha interna não revelada e token de convite armazenável por hash."""
    random_password = secrets.token_urlsafe(48)
    raw_token = secrets.token_urlsafe(32)
    return {
        "password_hash": generate_password_hash(random_password),
        "raw_token": raw_token,
        "token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
    }
