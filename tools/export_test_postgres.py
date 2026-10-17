"""Exporta PostgreSQL sintético descartável; a URL vem somente do ambiente."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.continuity_postgres import export_custom

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--target",required=True); parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({"dry_run":True,"target":Path(args.target).name})); return 0
    target=export_custom(os.getenv("PHASE29_SOURCE_DATABASE_URL"),args.target)
    print(json.dumps({"dry_run":False,"artifact":target.name,"bytes":target.stat().st_size})); return 0
if __name__=="__main__":sys.exit(main())
