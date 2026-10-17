"""Redrive controlado: plano por padrão e execução idempotente em isolamento."""
import psycopg2.extras
from services.attachment_queue import InvalidScanMessage,parse_scan_payload
from services.attachment_observability import emit,metric

class RedriveError(RuntimeError): pass

def redrive_messages(connection_factory,source,destination,execute=False,authorized=False,reason=None,batch_size=10,max_failures=1):
    limit=min(max(int(batch_size),1),100)
    stats=source.stats(); plan={"dry_run":not execute,"available":int(stats.get("dlq",stats.get("visible",0))),"moved":0,"rejected":0}
    if not execute: return plan
    if not authorized or not str(reason or "").strip(): raise RedriveError("Redrive exige autorização e motivo.")
    messages=source.receive(limit,0); failures=0
    for message in messages:
        try: payload=parse_scan_payload(message.body)
        except InvalidScanMessage:
            plan["rejected"]+=1; failures+=1
            if failures>=max_failures: break
            continue
        connection=connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT estado,empresa_id,anexo_id FROM anexo_varredura_jobs WHERE id=%s FOR UPDATE",(payload["job_id"],)); row=cursor.fetchone()
                valid=bool(row and str(row[1])==payload["company_id"] and str(row[2])==payload["attachment_id"] and row[0] not in {"concluido","falha_terminal"})
                if not valid: connection.rollback(); plan["rejected"]+=1; continue
                destination.send(message.body)
                cursor.execute("UPDATE anexo_varredura_jobs SET estado='pendente_publicacao',mensagem_id=NULL,proxima_tentativa_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=%s",(payload["job_id"],))
                cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                    VALUES(%s,NULL,'anexo.redrive_controlado','anexo_varredura_job',%s,%s)""",
                    (payload["company_id"],payload["job_id"],psycopg2.extras.Json({"job_id":payload["job_id"],"resultado":"redirecionado","motivo_codigo":"operacional"})))
                connection.commit()
            source.delete(message.receipt_handle); plan["moved"]+=1
        except Exception:
            connection.rollback(); failures+=1
            if failures>=max_failures: break
        finally: connection.close()
    plan["dry_run"]=False
    emit("redrive_completed",count=plan["moved"],result="partial" if failures else "ok")
    metric("RedriveProgress",plan["moved"],process="redrive",result="success")
    metric("RedriveFailures",failures,process="redrive",result="error")
    return plan
