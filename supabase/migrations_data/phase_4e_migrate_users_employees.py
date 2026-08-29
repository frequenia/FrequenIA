import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from uuid import UUID

import psycopg2
import psycopg2.extras


ALLOWED_PROFILES = {"funcionario", "gestor", "rh", "administrador"}
ALLOWED_CONTRACTS = {
    "efetivo",
    "comissionado",
    "temporario",
    "estagiario",
    "terceirizado",
    "outro",
}
ALLOWED_USER_STATUSES = {"ativo", "bloqueado", "inativo"}
ALLOWED_EMPLOYEE_STATUSES = {"ativo", "afastado", "desligado"}
COMPATIBLE_HASH_PREFIXES = ("scrypt:", "pbkdf2:")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
APPLY_CONFIRMATION = "FREQUENIA_PHASE_4E_APPLY"
ROLLBACK_CONFIRMATION = "FREQUENIA_PHASE_4E_ROLLBACK"


def normalize_cpf(value):
    return re.sub(r"\D", "", value or "")


def valid_cpf(value):
    cpf = normalize_cpf(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    numbers = [int(digit) for digit in cpf]
    total = sum(numbers[index] * (10 - index) for index in range(9))
    remainder = total % 11
    first = 0 if remainder < 2 else 11 - remainder
    total = sum(numbers[index] * (11 - index) for index in range(10))
    remainder = total % 11
    second = 0 if remainder < 2 else 11 - remainder
    return numbers[9:] == [first, second]


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_name(value):
    return " ".join((value or "").split()).casefold()


def valid_email(value):
    return bool(EMAIL_PATTERN.fullmatch(normalize_email(value)))


def masked_cpf(value):
    cpf = normalize_cpf(value)
    return f"***{cpf[-2:]}" if cpf else None


def masked_email(value):
    email = normalize_email(value)
    if "@" not in email:
        return "***invalid" if email else None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def hash_format(value):
    if not value:
        return "ausente"
    if value.startswith("scrypt:"):
        return "werkzeug-scrypt"
    if value.startswith("pbkdf2:"):
        return "werkzeug-pbkdf2"
    return "incompativel"


def canonical_uuid(value, field_name):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(f"Invalid UUID in mapping: {field_name}.") from exc


def read_json(path):
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("The mapping file must contain a JSON object.")
    return data


def require_environment(apply_mode=False):
    source_url = os.getenv("WORKSYNC_DATABASE_URL", "").strip()
    destination_url = os.getenv("DATABASE_URL", "").strip()
    source_ref = os.getenv("WORKSYNC_PROJECT_REF", "").strip()
    destination_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    app_env = os.getenv("APP_ENV", "").strip().lower()

    if not source_url or not destination_url:
        raise RuntimeError("WORKSYNC_DATABASE_URL and DATABASE_URL are required.")
    if not source_ref or not destination_ref or source_ref == destination_ref:
        raise RuntimeError("Source and destination project refs must be present and different.")
    if app_env not in {"development", "homologation"}:
        raise RuntimeError("Phase 4E is restricted to development/homologation.")
    if apply_mode and os.getenv("CONFIRM_PHASE_4E_MIGRATION") != APPLY_CONFIRMATION:
        raise RuntimeError("Explicit Phase 4E apply confirmation is required.")
    return source_url, destination_url


def load_source(connection, source_company_id):
    connection.set_session(readonly=True, autocommit=False)
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                u.id AS source_user_id,
                u.nome,
                u.email,
                u.telefone,
                u.cpf,
                u.senha_hash,
                u.status AS user_status,
                u.cargo_id AS source_role_id,
                u.setor_id AS source_sector_id,
                c.nome AS source_role_name,
                s.nome AS source_sector_name,
                f.id AS source_employee_id,
                f.matricula,
                f.data_admissao,
                f.tipo_contrato,
                f.carga_horaria,
                f.tipo_perfil
            FROM usuarios u
            LEFT JOIN funcionarios f ON f.usuario_id = u.id
            LEFT JOIN cargos c ON c.id = u.cargo_id
            LEFT JOIN setores s ON s.id = u.setor_id
            ORDER BY u.id, f.id
            """
        )
        records = cursor.fetchall()
        cursor.execute(
            """
            SELECT f.id
            FROM funcionarios f
            LEFT JOIN usuarios u ON u.id = f.usuario_id
            WHERE u.id IS NULL
            ORDER BY f.id
            """
        )
        orphan_employee_ids = [row["id"] for row in cursor.fetchall()]
        cursor.execute("SELECT 1 FROM empresas WHERE id = %s AND ativo = true", (source_company_id,))
        if not cursor.fetchone():
            raise RuntimeError("The approved source company does not exist or is inactive.")
    connection.rollback()
    return records, orphan_employee_ids


def load_destination(connection, readonly):
    connection.set_session(readonly=readonly, autocommit=False)
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("SELECT id, cpf, email FROM usuarios")
        users = cursor.fetchall()
        cursor.execute(
            """
            SELECT f.id, f.usuario_id, f.empresa_id, f.matricula
            FROM funcionarios f
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
    connection.rollback()
    return users, employees, catalog


def group_source(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["source_user_id"]].append(record)
    return grouped


def mapping_for(record, mapping, catalog_rows):
    sector_mapping = mapping.get("sector_mappings", {}).get(str(record["source_sector_id"]))
    role_mapping = mapping.get("role_mappings", {}).get(str(record["source_role_id"]))
    company_id = mapping.get("company_id")
    unit_mapping = mapping.get("unit", {})
    if not sector_mapping or not role_mapping or not company_id or not unit_mapping:
        return None

    company_id = canonical_uuid(company_id, "company_id")
    company_rows = [row for row in catalog_rows if str(row["empresa_id"]) == company_id]
    if not company_rows:
        return None

    unit_name = " ".join(str(unit_mapping.get("name") or "").split())
    team_name = " ".join(str(sector_mapping.get("team_name") or "").split())
    role_name = " ".join(str(role_mapping.get("cargo_name") or "").split())
    if not unit_name or not team_name or not role_name:
        return None

    unit_row = next(
        (row for row in company_rows if row["unidade_id"] and normalize_name(row["unidade_nome"]) == normalize_name(unit_name)),
        None,
    )
    team_row = next(
        (
            row
            for row in company_rows
            if unit_row
            and row["unidade_id"] == unit_row["unidade_id"]
            and row["equipe_id"]
            and normalize_name(row["equipe_nome"]) == normalize_name(team_name)
        ),
        None,
    )
    role_row = next(
        (row for row in company_rows if row["cargo_id"] and normalize_name(row["cargo_nome"]) == normalize_name(role_name)),
        None,
    )
    resolved = {
        "empresa_id": company_id,
        "empresa_nome": company_rows[0]["empresa_nome"],
        "unidade_id": str(unit_row["unidade_id"]) if unit_row else None,
        "unidade_nome": unit_name,
        "equipe_id": str(team_row["equipe_id"]) if team_row else None,
        "equipe_nome": team_name,
        "cargo_id": str(role_row["cargo_id"]) if role_row else None,
        "cargo_nome": role_name,
    }
    return resolved


def mapping_plan(mapping, catalog_rows):
    company_id = canonical_uuid(mapping.get("company_id"), "company_id")
    company_rows = [row for row in catalog_rows if str(row["empresa_id"]) == company_id]
    if not company_rows:
        raise RuntimeError("The approved destination company does not exist or is inactive.")
    unit_name = " ".join(str(mapping.get("unit", {}).get("name") or "").split())
    existing_unit = next(
        (row for row in company_rows if row["unidade_id"] and normalize_name(row["unidade_nome"]) == normalize_name(unit_name)),
        None,
    )
    sectors = []
    for source_id, item in mapping.get("sector_mappings", {}).items():
        team_name = " ".join(str(item.get("team_name") or "").split())
        existing_team = next(
            (
                row
                for row in company_rows
                if existing_unit
                and row["unidade_id"] == existing_unit["unidade_id"]
                and row["equipe_id"]
                and normalize_name(row["equipe_nome"]) == normalize_name(team_name)
            ),
            None,
        )
        sectors.append({"source_sector_id": int(source_id), "source": item.get("source_name"), "destination_team": team_name, "state": "existing" if existing_team else "planned"})
    roles = []
    for source_id, item in mapping.get("role_mappings", {}).items():
        role_name = " ".join(str(item.get("cargo_name") or "").split())
        existing_role = next(
            (row for row in company_rows if row["cargo_id"] and normalize_name(row["cargo_nome"]) == normalize_name(role_name)),
            None,
        )
        roles.append({"source_role_id": int(source_id), "source": item.get("source_name"), "destination_role": role_name, "state": "existing" if existing_role else "planned"})
    return {
        "source_company_id": mapping.get("source_company_id"),
        "company": {"id": company_id, "name": company_rows[0]["empresa_nome"], "state": "existing"},
        "unit": {"name": unit_name, "state": "existing" if existing_unit else "planned"},
        "sectors_to_teams": sectors,
        "roles": roles,
        "profiles": mapping.get("profile_mappings", {}),
        "contracts": mapping.get("contract_mappings", {}),
        "statuses": mapping.get("status_mappings", {}),
    }


def classify(records, orphan_employee_ids, destination, mapping):
    destination_users, destination_employees, catalog_rows = destination
    source_groups = group_source(records)
    source_cpfs = Counter(normalize_cpf(rows[0]["cpf"]) for rows in source_groups.values())
    source_emails = Counter(normalize_email(rows[0]["email"]) for rows in source_groups.values())
    source_employee_numbers = Counter(
        (rows[0]["matricula"] or "").strip().casefold()
        for rows in source_groups.values()
        if (rows[0]["matricula"] or "").strip()
    )
    authorized = {int(value) for value in mapping.get("authorized_source_user_ids", [])}
    destination_by_cpf = {normalize_cpf(row["cpf"]): row for row in destination_users}
    destination_by_email = {
        normalize_email(row["email"]): row for row in destination_users if normalize_email(row["email"])
    }
    employee_by_user = defaultdict(list)
    for employee in destination_employees:
        employee_by_user[str(employee["usuario_id"])].append(employee)

    results = []
    for source_user_id, rows in source_groups.items():
        record = rows[0]
        blockers = []
        reviews = []
        cpf = normalize_cpf(record["cpf"])
        email = normalize_email(record["email"])

        if len(rows) != 1 or not record["source_employee_id"]:
            blockers.append("employee_link_not_one_to_one")
        if not valid_cpf(cpf):
            blockers.append("invalid_cpf")
        if source_cpfs[cpf] > 1:
            blockers.append("duplicate_source_cpf")
        if not valid_email(email):
            blockers.append("invalid_email")
        if source_emails[email] > 1:
            blockers.append("duplicate_source_email")
        if not (record["matricula"] or "").strip():
            blockers.append("missing_employee_number")
        elif source_employee_numbers[record["matricula"].strip().casefold()] > 1:
            blockers.append("duplicate_source_employee_number")
        if not record["senha_hash"]:
            blockers.append("missing_password_hash")
        elif not record["senha_hash"].startswith(COMPATIBLE_HASH_PREFIXES):
            blockers.append("incompatible_password_hash")

        cpf_match = destination_by_cpf.get(cpf)
        email_match = destination_by_email.get(email)
        if cpf_match and email_match and cpf_match["id"] != email_match["id"]:
            blockers.append("destination_identity_conflict")
        existing_user = cpf_match or email_match
        if existing_user and (normalize_cpf(existing_user["cpf"]) != cpf or normalize_email(existing_user["email"]) != email):
            blockers.append("destination_identity_conflict")

        profile = mapping.get("profile_mappings", {}).get(str(record["tipo_perfil"]))
        contract = mapping.get("contract_mappings", {}).get(str(record["tipo_contrato"]))
        statuses = mapping.get("status_mappings", {}).get(str(record["user_status"]))
        structure = mapping_for(record, mapping, catalog_rows)
        if source_user_id not in authorized:
            reviews.append("not_authorized")
        if profile not in ALLOWED_PROFILES:
            reviews.append("profile_mapping_required")
        if contract not in ALLOWED_CONTRACTS:
            reviews.append("contract_mapping_required")
        if not statuses or statuses.get("user") not in ALLOWED_USER_STATUSES or statuses.get("employee") not in ALLOWED_EMPLOYEE_STATUSES:
            reviews.append("status_mapping_required")
        if not structure:
            reviews.append("organization_mapping_required")

        existing_employee = None
        if existing_user and structure:
            candidates = employee_by_user.get(str(existing_user["id"]), [])
            existing_employee = next(
                (
                    employee
                    for employee in candidates
                    if str(employee["empresa_id"]) == structure["empresa_id"]
                    and employee["matricula"].strip().casefold()
                    == record["matricula"].strip().casefold()
                ),
                None,
            )
        if structure and (record["matricula"] or "").strip():
            employee_number_conflict = next(
                (
                    employee
                    for employee in destination_employees
                    if str(employee["empresa_id"]) == structure["empresa_id"]
                    and employee["matricula"].strip().casefold()
                    == record["matricula"].strip().casefold()
                    and (not existing_user or employee["usuario_id"] != existing_user["id"])
                ),
                None,
            )
            if employee_number_conflict:
                blockers.append("destination_employee_number_conflict")

        if blockers:
            category = "bloquear"
        elif existing_user and existing_employee:
            category = "ja_existente"
        elif reviews:
            category = "revisar"
        else:
            category = "migrar"

        results.append(
            {
                "source_user_id": source_user_id,
                "source_employee_id": record["source_employee_id"],
                "cpf": masked_cpf(cpf),
                "email": masked_email(email),
                "hash_format": hash_format(record["senha_hash"]),
                "category": category,
                "reasons": sorted(set(blockers + reviews)),
                "record": record,
                "resolved": {
                    "profile": profile,
                    "contract": contract,
                    "statuses": statuses,
                    "structure": structure,
                    "existing_user_id": str(existing_user["id"]) if existing_user else None,
                    "existing_employee_id": str(existing_employee["id"]) if existing_employee else None,
                },
            }
        )
    return results, orphan_employee_ids


def sanitized_report(results, orphan_employee_ids, mode, plan):
    counts = Counter(result["category"] for result in results)
    return {
        "mode": mode,
        "total_read": len(results),
        "migrar": counts["migrar"],
        "ja_existente": counts["ja_existente"],
        "bloquear": counts["bloquear"],
        "revisar": counts["revisar"],
        "conflicts": sum(
            any("conflict" in reason or "duplicate" in reason for reason in result["reasons"])
            for result in results
        ),
        "mapping_plan": plan,
        "fixture_collisions": {
            "identity": sum(
                "destination_identity_conflict" in result["reasons"] for result in results
            ),
            "employee_number": sum(
                "destination_employee_number_conflict" in result["reasons"] for result in results
            ),
        },
        "orphan_source_employee_ids": orphan_employee_ids,
        "records": [
            {key: result[key] for key in ("source_user_id", "source_employee_id", "cpf", "email", "hash_format", "category", "reasons")}
            for result in results
        ],
    }


def validate_apply_scope(results, mapping):
    authorized_users = {int(value) for value in mapping.get("authorized_source_user_ids", [])}
    authorized_employees = {
        int(value) for value in mapping.get("authorized_source_employee_ids", [])
    }
    eligible = [result for result in results if result["category"] == "migrar"]
    eligible_users = {result["source_user_id"] for result in eligible}
    eligible_employees = {result["source_employee_id"] for result in eligible}
    if len(authorized_users) != 4 or len(authorized_employees) != 4:
        raise RuntimeError("Apply scope must contain exactly four authorized users and employees.")
    if eligible_users != authorized_users or eligible_employees != authorized_employees:
        raise RuntimeError("Current preflight diverges from the approved Phase 4E scope.")
    if any(
        "conflict" in reason or "duplicate" in reason
        for result in results
        for reason in result["reasons"]
    ):
        raise RuntimeError("Current preflight contains a conflict or duplicate.")


def materialize_structure(cursor, structure, manifest):
    if structure["unidade_id"]:
        unit_id = structure["unidade_id"]
    else:
        cursor.execute(
            """
            SELECT id FROM unidades
            WHERE empresa_id = %s AND lower(btrim(nome)) = lower(btrim(%s))
            """,
            (structure["empresa_id"], structure["unidade_nome"]),
        )
        row = cursor.fetchone()
        if row:
            unit_id = str(row["id"])
        else:
            cursor.execute(
                "INSERT INTO unidades (empresa_id, nome) VALUES (%s, %s) RETURNING id",
                (structure["empresa_id"], structure["unidade_nome"]),
            )
            unit_id = str(cursor.fetchone()["id"])
            manifest["created_units"].append(unit_id)

    if structure["equipe_id"]:
        team_id = structure["equipe_id"]
    else:
        cursor.execute(
            """
            SELECT id FROM equipes
            WHERE empresa_id = %s AND unidade_id = %s
              AND lower(btrim(nome)) = lower(btrim(%s))
            """,
            (structure["empresa_id"], unit_id, structure["equipe_nome"]),
        )
        row = cursor.fetchone()
        if row:
            team_id = str(row["id"])
        else:
            cursor.execute(
                """
                INSERT INTO equipes (empresa_id, unidade_id, nome)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (structure["empresa_id"], unit_id, structure["equipe_nome"]),
            )
            team_id = str(cursor.fetchone()["id"])
            manifest["created_teams"].append(team_id)

    if structure["cargo_id"]:
        role_id = structure["cargo_id"]
    else:
        cursor.execute(
            """
            SELECT id FROM cargos
            WHERE empresa_id = %s AND lower(btrim(nome)) = lower(btrim(%s))
            """,
            (structure["empresa_id"], structure["cargo_nome"]),
        )
        row = cursor.fetchone()
        if row:
            role_id = str(row["id"])
        else:
            cursor.execute(
                "INSERT INTO cargos (empresa_id, nome) VALUES (%s, %s) RETURNING id",
                (structure["empresa_id"], structure["cargo_nome"]),
            )
            role_id = str(cursor.fetchone()["id"])
            manifest["created_roles"].append(role_id)

    return {
        "empresa_id": structure["empresa_id"],
        "unidade_id": unit_id,
        "equipe_id": team_id,
        "cargo_id": role_id,
    }


def apply_migration(connection, results, manifest_path):
    eligible = [result for result in results if result["category"] == "migrar"]
    manifest = {
        "phase": "4E",
        "created_users": [],
        "created_employees": [],
        "created_units": [],
        "created_teams": [],
        "created_roles": [],
    }
    manifest_file = Path(manifest_path)
    if manifest_file.exists():
        raise RuntimeError("The rollback manifest already exists; apply cancelled.")
    manifest_written = False
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            for result in eligible:
                record = result["record"]
                resolved = result["resolved"]
                existing_user_id = resolved["existing_user_id"]
                if existing_user_id:
                    user_id = existing_user_id
                else:
                    cursor.execute(
                        """
                        INSERT INTO usuarios (nome, cpf, email, telefone, senha_hash, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            record["nome"].strip(),
                            normalize_cpf(record["cpf"]),
                            normalize_email(record["email"]),
                            (record["telefone"] or "").strip() or None,
                            record["senha_hash"],
                            resolved["statuses"]["user"],
                        ),
                    )
                    user_id = str(cursor.fetchone()["id"])
                    manifest["created_users"].append(user_id)

                structure = materialize_structure(cursor, resolved["structure"], manifest)
                cursor.execute(
                    """
                    INSERT INTO funcionarios (
                        usuario_id, empresa_id, unidade_id, equipe_id, cargo_id,
                        matricula, data_admissao, tipo_contrato,
                        carga_horaria_semanal, perfil, status
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                        resolved["statuses"]["employee"],
                    ),
                )
                manifest["created_employees"].append(str(cursor.fetchone()["id"]))
        with manifest_file.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        manifest_written = True
        connection.commit()
    except Exception:
        connection.rollback()
        if manifest_written:
            manifest_file.unlink(missing_ok=True)
        raise
    return len(eligible)


def rollback(destination_url, manifest_path):
    if os.getenv("CONFIRM_PHASE_4E_ROLLBACK") != ROLLBACK_CONFIRMATION:
        raise RuntimeError("Explicit Phase 4E rollback confirmation is required.")
    manifest = read_json(manifest_path)
    if manifest.get("phase") != "4E":
        raise RuntimeError("Invalid rollback manifest.")
    employee_ids = [canonical_uuid(value, "created employee") for value in manifest.get("created_employees", [])]
    user_ids = [canonical_uuid(value, "created user") for value in manifest.get("created_users", [])]
    team_ids = [canonical_uuid(value, "created team") for value in manifest.get("created_teams", [])]
    role_ids = [canonical_uuid(value, "created role") for value in manifest.get("created_roles", [])]
    unit_ids = [canonical_uuid(value, "created unit") for value in manifest.get("created_units", [])]
    with closing(psycopg2.connect(destination_url, sslmode="require", connect_timeout=15)) as connection:
        with connection:
            with connection.cursor() as cursor:
                if employee_ids:
                    cursor.execute("DELETE FROM funcionarios WHERE id = ANY(%s::uuid[])", (employee_ids,))
                    if cursor.rowcount != len(employee_ids):
                        raise RuntimeError("Rollback employee manifest does not match destination.")
                if user_ids:
                    cursor.execute("DELETE FROM usuarios WHERE id = ANY(%s::uuid[])", (user_ids,))
                    if cursor.rowcount != len(user_ids):
                        raise RuntimeError("Rollback user manifest does not match destination.")
                if team_ids:
                    cursor.execute("DELETE FROM equipes WHERE id = ANY(%s::uuid[])", (team_ids,))
                    if cursor.rowcount != len(team_ids):
                        raise RuntimeError("Rollback team manifest does not match destination.")
                if role_ids:
                    cursor.execute("DELETE FROM cargos WHERE id = ANY(%s::uuid[])", (role_ids,))
                    if cursor.rowcount != len(role_ids):
                        raise RuntimeError("Rollback role manifest does not match destination.")
                if unit_ids:
                    cursor.execute("DELETE FROM unidades WHERE id = ANY(%s::uuid[])", (unit_ids,))
                    if cursor.rowcount != len(unit_ids):
                        raise RuntimeError("Rollback unit manifest does not match destination.")
    print(json.dumps({"mode": "rollback", "employees_removed": len(employee_ids), "users_removed": len(user_ids), "teams_removed": len(team_ids), "roles_removed": len(role_ids), "units_removed": len(unit_ids)}))


def main():
    parser = argparse.ArgumentParser(description="FrequenIA Phase 4E controlled migration")
    parser.add_argument("--mapping", help="Reviewed JSON mapping file")
    parser.add_argument("--apply", action="store_true", help="Apply eligible records")
    parser.add_argument("--rollback", action="store_true", help="Rollback records from a manifest")
    parser.add_argument("--manifest", default="phase_4e_manifest.json")
    args = parser.parse_args()
    if args.apply and args.rollback:
        raise RuntimeError("Choose either --apply or --rollback.")

    source_url, destination_url = require_environment(apply_mode=args.apply)
    if args.rollback:
        rollback(destination_url, args.manifest)
        return

    mapping = read_json(args.mapping)
    with closing(psycopg2.connect(source_url, sslmode="require", connect_timeout=15)) as source:
        records, orphan_employee_ids = load_source(source, mapping.get("source_company_id"))
    with closing(psycopg2.connect(destination_url, sslmode="require", connect_timeout=15)) as destination:
        destination_state = load_destination(destination, readonly=not args.apply)
        results, orphan_employee_ids = classify(records, orphan_employee_ids, destination_state, mapping)
        plan = mapping_plan(mapping, destination_state[2])
        report = sanitized_report(results, orphan_employee_ids, "apply" if args.apply else "dry-run", plan)
        if args.apply:
            validate_apply_scope(results, mapping)
            report["migrated"] = apply_migration(destination, results, args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
