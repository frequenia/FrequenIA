"""Outbox transacional para publicação dos jobs de varredura."""

import os
import time

import psycopg2.extras

from services.attachment_observability import Timer, emit, metric
from services.attachment_queue import build_scan_payload, get_attachment_queue


class OutboxDispatchError(Exception):
    pass


def _audit_job(cursor,row,action,state,message_id=None):
    metadata={"job_id":str(row["id"]),"anexo_id":str(row["anexo_id"]),"estado":state}
    if message_id: metadata["mensagem_id"]=str(message_id)[:128]
    cursor.execute(
        """INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
           VALUES(%s,NULL,%s,'anexo_varredura_job',%s,%s)""",
        (row["empresa_id"],action,row["id"],psycopg2.extras.Json(metadata)),
    )


def asynchronous_scan_enabled():
    mode = os.getenv("ATTACHMENT_SCAN_MODE", "async").strip().lower()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if mode == "sync":
        if environment not in {"test", "testing"}:
            raise OutboxDispatchError("Varredura síncrona só é permitida em testes.")
        return False
    if mode != "async":
        raise OutboxDispatchError("Modo de varredura inválido.")
    return True


def create_scan_job(cursor, company_id, attachment_id):
    cursor.execute(
        """INSERT INTO anexo_varredura_jobs (empresa_id, anexo_id)
           VALUES (%s,%s)
           ON CONFLICT (anexo_id) DO UPDATE SET
             estado=CASE
               WHEN anexo_varredura_jobs.estado IN ('concluido','falha_terminal')
                 THEN anexo_varredura_jobs.estado
               ELSE 'pendente_publicacao'
             END,
             proxima_tentativa_at=CASE
               WHEN anexo_varredura_jobs.estado IN ('concluido','falha_terminal')
                 THEN anexo_varredura_jobs.proxima_tentativa_at
               ELSE clock_timestamp()
             END,
             updated_at=clock_timestamp()
           RETURNING *""",
        (company_id, attachment_id),
    )
    row = cursor.fetchone()
    emit("scan_job_created", result="pending")
    metric("ScanJobsCreated", 1, process="web", result="pending")
    return row


def requeue_scan_job(cursor, company_id, attachment_id):
    cursor.execute(
        """UPDATE anexo_varredura_jobs
           SET estado='pendente_publicacao', proxima_tentativa_at=clock_timestamp(),
               erro_codigo=NULL, mensagem_id=NULL, updated_at=clock_timestamp()
           WHERE empresa_id=%s AND anexo_id=%s
           RETURNING *""",
        (company_id, attachment_id),
    )
    row = cursor.fetchone()
    if row:
        return row
    return create_scan_job(cursor, company_id, attachment_id)


def _backoff_seconds(attempt):
    try:
        maximum = min(max(int(os.getenv("ATTACHMENT_OUTBOX_MAX_BACKOFF_SECONDS", "300")), 5), 3600)
    except ValueError:
        maximum = 300
    return min(maximum, 2 ** min(max(int(attempt), 1), 10))


def dispatch_pending(connection_factory, queue=None, batch_size=10):
    queue = queue or get_attachment_queue()
    limit = min(max(int(batch_size), 1), 100)
    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    result = {"selected": 0, "published": 0, "failed": 0}
    try:
        cursor.execute(
            """SELECT count(*) AS total,
                      coalesce(extract(epoch FROM (clock_timestamp()-min(created_at))),0) AS oldest
               FROM anexo_varredura_jobs
               WHERE estado IN ('pendente_publicacao','falha_reprocessavel')"""
        )
        backlog=cursor.fetchone()
        metric("OutboxBacklog",backlog["total"],process="dispatcher",result="observed")
        metric("OldestJobAge",backlog["oldest"],unit="Seconds",process="dispatcher",result="observed")
        cursor.execute(
            """SELECT * FROM anexo_varredura_jobs
               WHERE estado IN ('pendente_publicacao','falha_reprocessavel')
                 AND proxima_tentativa_at <= clock_timestamp()
               ORDER BY proxima_tentativa_at, created_at, id
               FOR UPDATE SKIP LOCKED LIMIT %s""",
            (limit,),
        )
        rows = cursor.fetchall()
        result["selected"] = len(rows)
        for row in rows:
            body = build_scan_payload(row["id"], row["anexo_id"], row["empresa_id"])
            try:
                with Timer() as timer:
                    message_id = queue.send(body)
                cursor.execute(
                    """UPDATE anexo_varredura_jobs
                       SET estado='publicado', mensagem_id=%s,
                           publicacao_tentativas=publicacao_tentativas+1,
                           publicado_at=clock_timestamp(), erro_codigo=NULL,
                           updated_at=clock_timestamp()
                       WHERE id=%s""",
                    (message_id, row["id"]),
                )
                _audit_job(cursor,row,"correcao.anexo_job_publicado","publicado",message_id)
                result["published"] += 1
                metric("ScanJobsPublished", 1, process="dispatcher", result="success")
                metric("PublishDuration", timer.duration_ms, unit="Milliseconds", process="dispatcher", result="success")
            except Exception as exc:
                attempt = row["publicacao_tentativas"] + 1
                cursor.execute(
                    """UPDATE anexo_varredura_jobs
                       SET estado='falha_reprocessavel',
                           publicacao_tentativas=publicacao_tentativas+1,
                           proxima_tentativa_at=clock_timestamp()+(%s * interval '1 second'),
                           erro_codigo='queue_unavailable', updated_at=clock_timestamp()
                       WHERE id=%s""",
                    (_backoff_seconds(attempt), row["id"]),
                )
                _audit_job(cursor,row,"correcao.anexo_job_publicacao_falha","falha_reprocessavel")
                result["failed"] += 1
                metric("ScanJobsFailed", 1, process="dispatcher", result="transient")
                connection.commit()
                raise OutboxDispatchError("Falha ao publicar job de varredura.") from exc
        connection.commit()
        emit("outbox_dispatch_completed", count=result["published"], result="ok")
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def run_dispatcher(connection_factory, queue=None, once=True, batch_size=10, poll_seconds=2, stop_event=None):
    while not (stop_event and stop_event.is_set()):
        dispatch_pending(connection_factory, queue=queue, batch_size=batch_size)
        if once:
            return
        if stop_event:
            stop_event.wait(max(float(poll_seconds), 0.1))
        else:
            time.sleep(max(float(poll_seconds), 0.1))
