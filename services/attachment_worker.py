"""Worker separado e idempotente para varreduras entregues ao menos uma vez."""

from dataclasses import dataclass
import os
import signal
import threading
import time

import psycopg2.extras

from services.attachment_observability import Timer, emit, metric
from services.attachment_queue import InvalidScanMessage, get_attachment_queue, parse_scan_payload
from services.attachment_scanner import ScannerError, get_attachment_scanner
from services.correction_attachments import scan_attachment


@dataclass(frozen=True)
class WorkerResult:
    acknowledge: bool
    outcome: str


def _audit_job(cursor,job,action,state):
    cursor.execute(
        """INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
           VALUES(%s,NULL,%s,'anexo_varredura_job',%s,%s)""",
        (job["empresa_id"],action,job["id"],psycopg2.extras.Json({
            "job_id":str(job["id"]),"anexo_id":str(job["anexo_id"]),"estado":state,
        })),
    )


def _visibility_seconds():
    scan_timeout = max(int(float(os.getenv("CLAMAV_TIMEOUT_SECONDS", "10"))), 1)
    configured = int(os.getenv("ATTACHMENT_QUEUE_VISIBILITY_SECONDS", "60"))
    if configured <= scan_timeout:
        raise RuntimeError("Visibility timeout deve superar o timeout da varredura.")
    return min(configured, 43200)


def _processing_lease_seconds():
    return min(max(int(os.getenv("ATTACHMENT_WORKER_LEASE_SECONDS", "120")), 30), 3600)


def process_message(connection_factory, queue, message, storage=None, scanner=None):
    try:
        payload = parse_scan_payload(message.body)
    except InvalidScanMessage:
        emit("scan_message_rejected", message_id=message.message_id, reason="invalid_payload")
        metric("ScanJobsFailed", 1, process="worker", result="invalid")
        return WorkerResult(False, "invalid")

    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(
            """SELECT j.*,a.estado AS anexo_estado,a.estado_seguranca
               FROM anexo_varredura_jobs j
               JOIN anexos_correcao a ON a.id=j.anexo_id AND a.empresa_id=j.empresa_id
               WHERE j.id=%s FOR UPDATE OF j""",
            (payload["job_id"],),
        )
        job = cursor.fetchone()
        if not job or str(job["anexo_id"]) != payload["attachment_id"] or str(job["empresa_id"]) != payload["company_id"]:
            if job:
                cursor.execute(
                    """UPDATE anexo_varredura_jobs SET estado='falha_terminal',
                       erro_codigo='invalid_payload',updated_at=clock_timestamp() WHERE id=%s""",
                    (job["id"],),
                )
                _audit_job(cursor,job,"correcao.anexo_job_mensagem_invalida","falha_terminal")
                connection.commit()
            return WorkerResult(False, "invalid")
        if job["estado"] in {"concluido", "falha_terminal"}:
            connection.commit()
            return WorkerResult(True, "duplicate_terminal")
        if job["estado"] == "processando":
            cursor.execute(
                "SELECT updated_at < clock_timestamp()-(%s * interval '1 second') AS expired FROM anexo_varredura_jobs WHERE id=%s",
                (_processing_lease_seconds(), job["id"]),
            )
            if not cursor.fetchone()["expired"]:
                connection.commit()
                return WorkerResult(False, "already_processing")
        if job["anexo_estado"] != "ativo" or job["estado_seguranca"] in {"limpo", "infectado"}:
            cursor.execute(
                """UPDATE anexo_varredura_jobs SET estado='concluido',concluido_at=clock_timestamp(),
                   erro_codigo=NULL,updated_at=clock_timestamp() WHERE id=%s""",
                (job["id"],),
            )
            _audit_job(cursor,job,"correcao.anexo_job_concluido","concluido")
            connection.commit()
            return WorkerResult(True, "out_of_order_terminal")
        cursor.execute(
            """UPDATE anexo_varredura_jobs SET estado='processando',
               processamento_tentativas=processamento_tentativas+1,
               processamento_iniciado_at=clock_timestamp(),erro_codigo=NULL,
               updated_at=clock_timestamp() WHERE id=%s""",
            (job["id"],),
        )
        _audit_job(cursor,job,"correcao.anexo_job_consumo","processando")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    queue.change_visibility(message.receipt_handle, _visibility_seconds())
    auth = {"empresa_id": payload["company_id"], "user_id": None, "perfil": "sistema"}
    try:
        with Timer() as timer:
            attachment = scan_attachment(
                connection_factory,
                auth,
                payload["attachment_id"],
                storage=storage,
                scanner=scanner,
                management=False,
            )
    except Exception:
        _mark_retryable(connection_factory, payload["job_id"], "processing_failed")
        metric("ScanJobsFailed", 1, process="worker", result="transient")
        return WorkerResult(False, "transient")

    if attachment["estado_seguranca"] == "erro_varredura":
        _mark_retryable(connection_factory, payload["job_id"], "scan_unavailable")
        metric("ScanJobsFailed", 1, process="worker", result="transient")
        return WorkerResult(False, "transient")
    if attachment["estado_seguranca"] not in {"limpo", "infectado"}:
        _mark_retryable(connection_factory, payload["job_id"], "unknown_state")
        return WorkerResult(False, "transient")

    connection = connection_factory()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """UPDATE anexo_varredura_jobs SET estado='concluido',
                   concluido_at=clock_timestamp(),erro_codigo=NULL,updated_at=clock_timestamp()
                   WHERE id=%s""",
                (payload["job_id"],),
            )
            cursor.execute("SELECT * FROM anexo_varredura_jobs WHERE id=%s",(payload["job_id"],))
            terminal_job=cursor.fetchone()
            _audit_job(cursor,terminal_job,"correcao.anexo_job_concluido","concluido")
        connection.commit()
    except Exception:
        connection.rollback()
        return WorkerResult(False, "persistence_failed")
    finally:
        connection.close()
    metric("ScanDuration", timer.duration_ms, unit="Milliseconds", process="worker", result=attachment["estado_seguranca"])
    metric("ScanJobsCompleted", 1, process="worker", result=attachment["estado_seguranca"])
    emit("scan_job_completed", job_id=payload["job_id"], attachment_id=payload["attachment_id"], result=attachment["estado_seguranca"], duration_ms=timer.duration_ms)
    return WorkerResult(True, attachment["estado_seguranca"])


def _mark_retryable(connection_factory, job_id, code):
    connection = connection_factory()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """UPDATE anexo_varredura_jobs SET estado='falha_reprocessavel',
                   erro_codigo=%s,proxima_tentativa_at=clock_timestamp()+interval '30 seconds',
                   updated_at=clock_timestamp() WHERE id=%s RETURNING *""",
                (code, job_id),
            )
            job=cursor.fetchone()
            if job: _audit_job(cursor,job,"correcao.anexo_job_falha","falha_reprocessavel")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def worker_ready(scanner=None):
    try:
        scanner = scanner or get_attachment_scanner()
        if not scanner.healthcheck():
            metric("ScannerAvailable", 0, process="worker", result="unavailable")
            return False
        info=scanner.signature_info()
        metric("ClamAVSignatureAge", info.age_hours, unit="Hours", process="worker", result="observed")
        current=scanner.signatures_current()
        metric("ScannerAvailable", 1 if current else 0, process="worker", result="ready" if current else "stale")
        return bool(current)
    except ScannerError:
        return False


def run_worker(connection_factory, queue=None, storage=None, scanner=None, once=False, stop_event=None):
    queue = queue or get_attachment_queue()
    stop_event = stop_event or threading.Event()
    batch_size = min(max(int(os.getenv("ATTACHMENT_WORKER_BATCH_SIZE", "2")), 1), 10)
    while not stop_event.is_set():
        stats=queue.stats()
        metric("QueueVisible",stats.get("visible",0),process="worker",result="observed")
        metric("QueueInFlight",stats.get("inflight",0),process="worker",result="observed")
        if "dlq" in stats: metric("DlqMessages",stats["dlq"],process="worker",result="observed")
        messages = queue.receive(batch_size, 20 if not once else 0)
        for message in messages:
            if stop_event.is_set():
                break
            result = process_message(connection_factory, queue, message, storage=storage, scanner=scanner)
            if result.acknowledge:
                queue.delete(message.receipt_handle)
        metric("WorkerHeartbeat", 1, process="worker", result="ok")
        if once:
            return


def install_shutdown_handlers(stop_event):
    def stop(_signum, _frame):
        stop_event.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
