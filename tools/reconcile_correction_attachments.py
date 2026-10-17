"""Executa reconciliação sanitizada; dry-run é o padrão."""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from db import conectar_bd
from services.attachment_reconciliation import reconcile_attachments


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--company-id")
    parser.add_argument("--batch-size",type=int,default=100)
    parser.add_argument("--after-id")
    parser.add_argument("--repair",choices=["requeue-missing-job"])
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    company_id=str(UUID(args.company_id)) if args.company_id else None
    result=reconcile_attachments(conectar_bd,company_id=company_id,batch_size=args.batch_size,
                                 after_id=args.after_id,repair=args.repair,execute=args.execute)
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    sys.exit(main())
