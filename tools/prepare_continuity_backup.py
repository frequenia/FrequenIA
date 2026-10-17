"""Prepara conjunto sintético fora do repositório; dry-run é o padrão."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.continuity_backup import prepare_backup_set

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--destination",required=True); parser.add_argument("--artifact",action="append",default=[])
    parser.add_argument("--component",action="append",default=[]); parser.add_argument("--environment",default="test"); parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if len(args.artifact)!=len(args.component): parser.error("cada --artifact exige um --component")
    result=prepare_backup_set(args.destination,[{"source":path,"component":component} for path,component in zip(args.artifact,args.component)],[],args.environment,args.execute)
    print(json.dumps(result,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
