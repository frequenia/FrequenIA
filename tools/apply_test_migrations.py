"""Aplica todas as migrations somente no PostgreSQL descartável homologado."""

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2


ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = "frequenia_phase25_test"


def main():
    database_url = os.environ.get("PHASE26_TEST_DATABASE_URL", "").strip()
    parsed = urlparse(database_url)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != f"/{DATABASE_NAME}"
    ):
        raise SystemExit(
            "PHASE26_TEST_DATABASE_URL deve apontar para o banco local descartável "
            f"{DATABASE_NAME}."
        )
    migrations = sorted((ROOT / "supabase" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    numbers = [int(path.name[:3]) for path in migrations]
    if numbers != list(range(1, numbers[-1] + 1)):
        raise SystemExit("A sequência de migrations possui lacunas ou duplicidades.")
    connection = psycopg2.connect(database_url, connect_timeout=5)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("DROP SCHEMA IF EXISTS extensions CASCADE")
            cursor.execute("CREATE SCHEMA public")
            for migration in migrations:
                cursor.execute(migration.read_text(encoding="utf-8"))
    finally:
        connection.close()
    print(f"Aplicadas {len(migrations)} migrations (001-{numbers[-1]:03d}).")


if __name__ == "__main__":
    main()
