"""Restaura somente conjunto sintético verificado em destino isolado."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.continuity_backup import restore_backup_set
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--source",required=True); parser.add_argument("--destination",required=True)
    parser.add_argument("--environment",default="test"); parser.add_argument("--execute",action="store_true"); parser.add_argument("--allow-nonempty",action="store_true")
    args=parser.parse_args(); result=restore_backup_set(args.source,args.destination,args.environment,args.execute,args.allow_nonempty)
    print(json.dumps(result,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
