"""Processo separado para consumir a fila de varredura."""

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from db import conectar_bd
from services.attachment_worker import install_shutdown_handlers, run_worker, worker_ready


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    if not worker_ready():
        print("Worker não pronto: scanner ou assinaturas indisponíveis.",file=sys.stderr)
        return 2
    stop_event=threading.Event(); install_shutdown_handlers(stop_event)
    run_worker(conectar_bd,once=args.once,stop_event=stop_event)
    return 0


if __name__=="__main__":
    sys.exit(main())
