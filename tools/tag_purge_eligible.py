"""Autoriza em banco e aplica tags de lifecycle; ambas as etapas são dry-run por padrão."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import conectar_bd
from services.purge_eligibility import authorize_expired,apply_authorized_tags
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--batch-size",type=int,default=100); parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(); authorization=authorize_expired(conectar_bd,args.batch_size,args.execute)
    tagging=apply_authorized_tags(conectar_bd,batch_size=args.batch_size,execute=args.execute)
    print(json.dumps({"authorization":authorization,"tagging":tagging},sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
