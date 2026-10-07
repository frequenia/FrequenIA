"""Aplica de modo idempotente a migration 020 no DATABASE_URL configurado."""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


load_dotenv()
root = Path(__file__).resolve().parents[1]
sql = (root / "supabase/migrations/020_mobile_geofenced_clock.sql").read_text(
    encoding="utf-8"
)
connection = psycopg2.connect(
    os.environ["DATABASE_URL"], sslmode="require", connect_timeout=15
)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_schema='public' AND table_name='unidades'
                 AND column_name='marcacao_mobile_ativa'"""
        )
        already_applied = bool(cursor.fetchone()[0])
        print(f"migration_020_already_applied={already_applied}")
        if not already_applied:
            cursor.execute(sql)
        cursor.execute(
            """SELECT count(*) FROM information_schema.columns
               WHERE table_schema='public' AND table_name='marcacoes'
                 AND column_name IN (
                   'canal','latitude','longitude','precisao_metros',
                   'distancia_unidade_metros','localizacao_capturada_at'
                 )"""
        )
        verified_columns = cursor.fetchone()[0]
    connection.commit()
    print(f"verified_marking_location_columns={verified_columns}")
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
