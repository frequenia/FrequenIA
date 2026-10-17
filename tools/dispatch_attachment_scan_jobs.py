"""Publica o outbox de varredura; não executa dentro do processo web."""

import argparse
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from db import conectar_bd
from services.attachment_outbox import OutboxDispatchError, run_dispatcher


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--continuous",action="store_true")
    parser.add_argument("--batch-size",type=int,default=10)
    args=parser.parse_args()
    stop_event=threading.Event()
    def stop(_signum, _frame):
        stop_event.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        run_dispatcher(conectar_bd,once=not args.continuous,batch_size=args.batch_size,stop_event=stop_event)
        return 0
    except OutboxDispatchError as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
