"""Comando administrativo de purga; dry-run é o padrão."""
import argparse
import json
from db import conectar_bd
from services.attachment_purge import purge_expired

def main():
    parser=argparse.ArgumentParser(description="Purga anexos vencidos sem apagar metadados.")
    parser.add_argument("--execute",action="store_true",help="Executa remoções; sem a flag é dry-run.")
    parser.add_argument("--batch-size",type=int,default=100)
    args=parser.parse_args(); result=purge_expired(conectar_bd,execute=args.execute,batch_size=args.batch_size)
    print(json.dumps(result,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
