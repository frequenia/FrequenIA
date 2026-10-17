"""Eliminacao biometrica tenant-scoped; dry-run por padrao."""

import argparse
import json

from db import conectar_bd
from services.biometric_governance import purge_eligible


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    connection = conectar_bd()
    try:
        result = purge_eligible(
            connection, company_id=args.empresa_id, execute=args.execute, limit=args.limit
        )
        print(json.dumps(result, sort_keys=True))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
