"""Aplica de modo idempotente a migration 019 no DATABASE_URL configurado."""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


load_dotenv()
root = Path(__file__).resolve().parents[1]
sql = (root / "supabase/migrations/019_platform_admin_employee_onboarding.sql").read_text(
    encoding="utf-8"
)
connection = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require", connect_timeout=15)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'usuarios'
                 AND column_name = 'perfil_sistema'"""
        )
        already_applied = bool(cursor.fetchone()[0])
        print(f"migration_019_already_applied={already_applied}")
        if not already_applied:
            cursor.execute(sql)
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'usuarios'
                 AND column_name IN ('perfil_sistema', 'primeiro_acesso_pendente')
               ORDER BY column_name"""
        )
        columns = ",".join(row[0] for row in cursor.fetchall())
    connection.commit()
    print(f"verified_columns={columns}")
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
