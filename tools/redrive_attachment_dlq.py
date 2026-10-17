"""Contrato operacional de redrive: plano por padrão; execução usa adaptadores server-side."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import conectar_bd
from services.attachment_queue import get_attachment_queue,SQSAttachmentQueue
from services.controlled_redrive import redrive_messages

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--reason")
    parser.add_argument("--batch-size",type=int,default=10); parser.add_argument("--execute",action="store_true"); parser.add_argument("--authorized",action="store_true")
    args=parser.parse_args(); destination=get_attachment_queue()
    dlq_url=os.getenv("ATTACHMENT_DLQ_URL","").strip()
    if not dlq_url: parser.error("ATTACHMENT_DLQ_URL server-side é obrigatória")
    source=SQSAttachmentQueue(dlq_url)
    result=redrive_messages(conectar_bd,source,destination,args.execute,args.authorized,args.reason,args.batch_size)
    print(json.dumps(result,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
