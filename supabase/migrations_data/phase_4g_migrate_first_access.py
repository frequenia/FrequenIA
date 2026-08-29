import argparse
import hashlib
import json
import os
import secrets
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extras

from phase_4e_migrate_users_employees import (
    ALLOWED_CONTRACTS,
    ALLOWED_PROFILES,
    group_source,
    load_source,
    mapping_for,
    mapping_plan,
    materialize_structure,
    normalize_cpf,
    normalize_email,
    normalize_name,
    read_json,
    valid_cpf,
    valid_email,
)


EXPECTED_SOURCE_USERS = {34, 45, 49, 60}
EXPECTED_SOURCE_EMPLOYEES = {20, 30, 31, 39}
APPLY_CONFIRMATION = "FREQUENIA_PHASE_4G_APPLY"


def require_environment(apply_mode=False):
    source_url = os.getenv("WORKSYNC_DATABASE_URL", "").strip()
    destination_url = os.getenv("DATABASE_URL", "").strip()
    source_ref = os.getenv("WORKSYNC_PROJECT_REF", "").strip()
    destination_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    app_env = os.getenv("APP_ENV", "").strip().lower()

    if not source_url and os.getenv("DB_HOST"):
        source_url = "postgresql://{}:{}@{}:{}/{}".format(
            quote_plus(os.environ["DB_USER"]),
            quote_plus(os.environ["DB_PASSWORD"]),
            os.environ["DB_HOST"],
            os.getenv("DB_PORT", "5432"),
            os.environ["DB_NAME"],
        )
    if not destination_url and os.getenv("NEW_DB_HOST"):
        destination_url = "postgresql://{}:{}@{}:{}/{}".format(
            quote_plus(os.environ["NEW_DB_USER"]),
            quote_plus(os.environ["NEW_DB_PASSWORD"]),
            os.environ["NEW_DB_HOST"],
            os.getenv("NEW_DB_PORT", "5432"),
            os.environ["NEW_DB_NAME"],
        )
    if not source_ref and os.getenv("DB_HOST", "").startswith("db."):
        source_ref = os.environ["DB_HOST"].split(".", 2)[1]
    if not source_ref and "." in os.getenv("DB_USER", ""):
        source_ref = os.environ["DB_USER"].split(".", 1)[1]

    if not source_url or not destination_url:
        raise RuntimeError("WORKSYNC_DATABASE_URL and DATABASE_URL are required.")
    if not source_ref or not destination_ref or source_ref == destination_ref:
        raise RuntimeError("Source and destination project refs must be present and different.")
    if app_env not in {"development", "homologation"}:
        raise RuntimeError("Phase 4G is restricted to development/homologation.")
    if apply_mode:
        if os.getenv("CONFIRM_PHASE_4G_MIGRATION") != APPLY_CONFIRMATION:
            raise RuntimeError("Explicit Phase 4G apply confirmation is required.")

    try:
        token_minutes = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30"))
    except ValueError as exc:
        raise RuntimeError("PASSWORD_RESET_TOKEN_MINUTES must be a positive integer.") from exc
    if token_minutes <= 0:
        raise RuntimeError("PASSWORD_RESET_TOKEN_MINUTES must be a positive integer.")
    return source_url, destination_url, token_minutes


def validate_mapping(mapping):
    authorized_users = {int(value) for value in mapping.get("authorized_source_user_ids", [])}
    authorized_employees = {
        int(value) for value in mapping.get("authorized_source_employee_ids", [])
    }
    if authorized_users != EXPECTED_SOURCE_USERS:
        raise RuntimeError("The mapping must authorize exactly source users 34, 45, 49 and 60.")
    if authorized_employees != EXPECTED_SOURCE_EMPLOYEES:
        raise RuntimeError("The mapping must authorize exactly source employees 20, 30, 31 and 39.")
    if mapping.get("source_company_id") != 1:
        raise RuntimeError("The approved source company must be ID 1.")


def load_destination(connection, readonly):
    connection.set_session(readonly=readonly, autocommit=False)
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("SELECT id, cpf, email, senha_hash, status FROM usuarios")
        users = cursor.fetchall()
        cursor.execute(
            """
            SELECT id, usuario_id, empresa_id, matricula, status
            FROM funcionarios
            """
        )
        employees = cursor.fetchall()
        cursor.execute(
            """
            SELECT
                e.id AS empresa_id,
                e.nome AS empresa_nome,
                un.id AS unidade_id,
                un.nome AS unidade_nome,
                eq.id AS equipe_id,
                eq.nome AS equipe_nome,
                c.id AS cargo_id,
                c.nome AS cargo_nome
            FROM empresas e
            LEFT JOIN unidades un ON un.empresa_id = e.id AND un.status = 'ativa'
            LEFT JOIN equipes eq
                ON eq.empresa_id = e.id AND eq.unidade_id = un.id AND eq.status = 'ativa'
            LEFT JOIN cargos c ON c.empresa_id = e.id AND c.status = 'ativo'
            WHERE e.status = 'ativa'
            """
        )
        catalog = cursor.fetchall()
        cursor.execute(
            """
            SELECT usuario_id, count(*) AS active_tokens
            FROM password_reset_tokens
            WHERE purpose = 'first_access'
              AND used_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > now()
            GROUP BY usuario_id
            """
        )
        active_tokens = {
            str(row["usuario_id"]): row["active_tokens"] for row in cursor.fetchall()
        }
    connection.rollback()
    return users, employees, catalog, active_tokens


def classify(records, destination, mapping):
    destination_users, destination_employees, catalog, active_tokens = destination
    source_groups = group_source(records)
    source_cpfs = Counter(normalize_cpf(rows[0]["cpf"]) for rows in source_groups.values())
    source_emails = Counter(normalize_email(rows[0]["email"]) for rows in source_groups.values())
    source_numbers = Counter(
        (rows[0]["matricula"] or "").strip().casefold()
        for rows in source_groups.values()
        if (rows[0]["matricula"] or "").strip()
    )
    destination_by_cpf = {normalize_cpf(row["cpf"]): row for row in destination_users}
    destination_by_email = {
        normalize_email(row["email"]): row
        for row in destination_users
        if normalize_email(row["email"])
    }
    destination_numbers = {
        (str(row["empresa_id"]), row["matricula"].strip().casefold()): row
        for row in destination_employees
    }

    results = []
    for source_user_id in sorted(EXPECTED_SOURCE_USERS):
        rows = source_groups.get(source_user_id, [])
        blockers = []
        conflicts = []
        record = rows[0] if rows else None
        if len(rows) != 1 or not record or not record["source_employee_id"]:
            blockers.append("employee_link_not_one_to_one")
            results.append(
                {
                    "source_user_id": source_user_id,
                    "source_employee_id": None,
                    "category": "bloqueado",
                    "reasons": blockers,
                    "record": record,
                    "resolved": None,
                }
            )
            continue

        cpf = normalize_cpf(record["cpf"])
        email = normalize_email(record["email"])
        employee_number = (record["matricula"] or "").strip()
        if record["source_employee_id"] not in EXPECTED_SOURCE_EMPLOYEES:
            blockers.append("employee_not_authorized")
        if record["senha_hash"]:
            blockers.append("unexpected_password_hash")
        if not valid_cpf(cpf) or source_cpfs[cpf] != 1:
            blockers.append("invalid_or_duplicate_source_cpf")
        if not valid_email(email) or source_emails[email] != 1:
            blockers.append("invalid_or_duplicate_source_email")
        if not employee_number or source_numbers[employee_number.casefold()] != 1:
            blockers.append("invalid_or_duplicate_source_employee_number")

        profile = mapping.get("profile_mappings", {}).get(str(record["tipo_perfil"]))
        contract = mapping.get("contract_mappings", {}).get(str(record["tipo_contrato"]))
        sector_mapping = mapping.get("sector_mappings", {}).get(
            str(record["source_sector_id"])
        )
        role_mapping = mapping.get("role_mappings", {}).get(str(record["source_role_id"]))
        structure = mapping_for(record, mapping, catalog)
        if profile not in ALLOWED_PROFILES:
            blockers.append("profile_mapping_required")
        if contract not in ALLOWED_CONTRACTS:
            blockers.append("contract_mapping_required")
        if not structure:
            blockers.append("organization_mapping_required")
        if not sector_mapping or normalize_name(sector_mapping.get("source_name")) != normalize_name(
            record["source_sector_name"]
        ):
            blockers.append("source_sector_mapping_mismatch")
        if not role_mapping or normalize_name(role_mapping.get("source_name")) != normalize_name(
            record["source_role_name"]
        ):
            blockers.append("source_role_mapping_mismatch")

        cpf_match = destination_by_cpf.get(cpf)
        email_match = destination_by_email.get(email)
        if cpf_match and email_match and cpf_match["id"] != email_match["id"]:
            conflicts.append("destination_identity_conflict")
        existing_user = cpf_match or email_match
        if existing_user and (
            normalize_cpf(existing_user["cpf"]) != cpf
            or normalize_email(existing_user["email"]) != email
        ):
            conflicts.append("destination_identity_conflict")

        existing_employee = None
        employee_number_match = None
        if structure:
            employee_number_match = destination_numbers.get(
                (structure["empresa_id"], employee_number.casefold())
            )
        if existing_user:
            existing_employee = next(
                (
                    employee
                    for employee in destination_employees
                    if employee["usuario_id"] == existing_user["id"]
                    and structure
                    and str(employee["empresa_id"]) == structure["empresa_id"]
                    and employee["matricula"].strip().casefold()
                    == employee_number.casefold()
                ),
                None,
            )
            if not existing_employee:
                conflicts.append("destination_employee_link_conflict")
        if employee_number_match and (
            not existing_user or employee_number_match["usuario_id"] != existing_user["id"]
        ):
            conflicts.append("destination_employee_number_conflict")

        if blockers:
            category = "bloqueado"
        elif conflicts:
            category = "conflito"
        elif existing_user and existing_employee:
            category = "ja_existente"
            if existing_user["senha_hash"] is not None or existing_user["status"] != "bloqueado":
                conflicts.append("existing_user_not_pending_first_access")
            if existing_employee["status"] != "afastado":
                conflicts.append("existing_employee_not_pending_first_access")
            if active_tokens.get(str(existing_user["id"]), 0) != 1:
                conflicts.append("active_first_access_token_count_mismatch")
            if conflicts:
                category = "conflito"
        else:
            category = "criar"

        results.append(
            {
                "source_user_id": source_user_id,
                "source_employee_id": record["source_employee_id"],
                "category": category,
                "reasons": sorted(set(blockers + conflicts)),
                "record": record,
                "resolved": {
                    "profile": profile,
                    "contract": contract,
                    "structure": structure,
                    "existing_user_id": str(existing_user["id"]) if existing_user else None,
                    "existing_employee_id": (
                        str(existing_employee["id"]) if existing_employee else None
                    ),
                },
            }
        )
    return results


def sanitized_report(results, mode, plan):
    counts = Counter(result["category"] for result in results)
    structures_missing = {
        "unit": 1 if plan["unit"]["state"] == "planned" else 0,
        "teams": sum(item["state"] == "planned" for item in plan["sectors_to_teams"]),
        "roles": sum(item["state"] == "planned" for item in plan["roles"]),
    }
    return {
        "phase": "4G",
        "mode": mode,
        "authorized_users": 4,
        "authorized_employees": 4,
        "criar": counts["criar"],
        "ja_existente": counts["ja_existente"],
        "conflito": counts["conflito"],
        "bloqueado": counts["bloqueado"],
        "structures_missing": structures_missing,
        "first_access_tokens": {
            "purpose": "first_access",
            "would_generate": counts["criar"],
            "raw_tokens_reported": 0,
        },
        "mapping_plan": plan,
        "records": [
            {
                "source_user_id": result["source_user_id"],
                "source_employee_id": result["source_employee_id"],
                "category": result["category"],
                "reasons": result["reasons"],
            }
            for result in results
        ],
    }


def validate_apply_scope(results):
    if len(results) != 4 or any(result["category"] != "criar" for result in results):
        raise RuntimeError("Apply requires exactly four conflict-free records to create.")
    if {result["source_user_id"] for result in results} != EXPECTED_SOURCE_USERS:
        raise RuntimeError("The eligible source user scope diverged.")
    if {result["source_employee_id"] for result in results} != EXPECTED_SOURCE_EMPLOYEES:
        raise RuntimeError("The eligible source employee scope diverged.")


def apply_migration(connection, results, token_minutes, manifest_path):
    manifest_file = Path(manifest_path)
    if manifest_file.exists():
        raise RuntimeError("The Phase 4G manifest already exists; apply cancelled.")
    manifest = {
        "phase": "4G",
        "created_users": [],
        "created_employees": [],
        "created_tokens": [],
        "created_units": [],
        "created_teams": [],
        "created_roles": [],
    }
    manifest_written = False
    raw_tokens = []
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            for result in results:
                record = result["record"]
                resolved = result["resolved"]
                structure = materialize_structure(cursor, resolved["structure"], manifest)
                cursor.execute(
                    """
                    INSERT INTO usuarios (nome, cpf, email, telefone, senha_hash, status)
                    VALUES (%s, %s, %s, %s, NULL, 'bloqueado')
                    RETURNING id
                    """,
                    (
                        record["nome"].strip(),
                        normalize_cpf(record["cpf"]),
                        normalize_email(record["email"]),
                        (record["telefone"] or "").strip() or None,
                    ),
                )
                user_id = str(cursor.fetchone()["id"])
                manifest["created_users"].append(user_id)

                cursor.execute(
                    """
                    INSERT INTO funcionarios (
                        usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                        matricula, data_admissao, tipo_contrato,
                        carga_horaria_semanal, perfil, status
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'afastado')
                    RETURNING id
                    """,
                    (
                        user_id,
                        structure["empresa_id"],
                        structure["unidade_id"],
                        structure["equipe_id"],
                        structure["cargo_id"],
                        record["matricula"].strip(),
                        record["data_admissao"],
                        resolved["contract"],
                        record["carga_horaria"],
                        resolved["profile"],
                    ),
                )
                manifest["created_employees"].append(str(cursor.fetchone()["id"]))

                raw_token = secrets.token_urlsafe(32)
                raw_tokens.append(raw_token)
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO password_reset_tokens (
                        usuario_id, token_hash, purpose, expires_at
                    )
                    VALUES (
                        %s, %s, 'first_access',
                        now() + (%s * interval '1 minute')
                    )
                    RETURNING id
                    """,
                    (user_id, token_hash, token_minutes),
                )
                manifest["created_tokens"].append(str(cursor.fetchone()["id"]))

        with manifest_file.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        manifest_written = True
        connection.commit()
    except Exception:
        connection.rollback()
        if manifest_written:
            manifest_file.unlink(missing_ok=True)
        raise
    finally:
        for index in range(len(raw_tokens)):
            raw_tokens[index] = None
        raw_tokens.clear()
    return {
        "users_created": len(manifest["created_users"]),
        "employees_created": len(manifest["created_employees"]),
        "first_access_tokens_created": len(manifest["created_tokens"]),
        "raw_tokens_reported": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="FrequenIA Phase 4G controlled migration")
    parser.add_argument("--mapping", required=True, help="Reviewed Phase 4G mapping")
    parser.add_argument("--apply", action="store_true", help="Apply the approved migration")
    parser.add_argument(
        "--manifest", default="phase_4g_manifest.homologation.json", help="Internal ID manifest"
    )
    args = parser.parse_args()

    mapping = read_json(args.mapping)
    validate_mapping(mapping)
    source_url, destination_url, token_minutes = require_environment(args.apply)
    with closing(psycopg2.connect(source_url, sslmode="require", connect_timeout=15)) as source:
        records, _ = load_source(source, mapping["source_company_id"])
    with closing(psycopg2.connect(destination_url, sslmode="require", connect_timeout=15)) as destination:
        destination_state = load_destination(destination, readonly=not args.apply)
        results = classify(records, destination_state, mapping)
        plan = mapping_plan(mapping, destination_state[2])
        report = sanitized_report(results, "apply" if args.apply else "dry-run", plan)
        if args.apply:
            validate_apply_scope(results)
            report["applied"] = apply_migration(
                destination, results, token_minutes, args.manifest
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
