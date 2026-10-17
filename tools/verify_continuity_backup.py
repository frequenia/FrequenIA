"""Verifica manifesto e checksums antes de qualquer restore."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.backup_manifest import load_and_verify_manifest
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--source",required=True); args=parser.parse_args()
    manifest=load_and_verify_manifest(args.source)
    print(json.dumps({"set_id":manifest["set_id"],"verified":True,"items":manifest["item_count"]},sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
