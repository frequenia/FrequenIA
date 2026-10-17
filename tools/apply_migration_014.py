"""Aplica de modo idempotente a migration 014 no DATABASE_URL configurado."""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


load_dotenv()
root = Path(__file__).resolve().parents[1]
sql = (root / "supabase/migrations/014_manager_scopes.sql").read_text(encoding="utf-8")
connection = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require", connect_timeout=15)
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.gestores_escopos')")
        already_applied = cursor.fetchone()[0] is not None
        print(f"migration_014_already_applied={already_applied}")
        if not already_applied:
            cursor.execute(sql)
        cursor.execute("SELECT to_regclass('public.gestores_escopos')")
        verified = cursor.fetchone()[0] is not None
    connection.commit()
    print(f"gestores_escopos_verified={verified}")
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
