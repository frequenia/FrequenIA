"""Executor idempotente de retenção e purga de comprovantes."""
import os
import psycopg2.extras
from services.attachment_observability import emit
from services.correction_attachment_storage import AttachmentStorageError, get_attachment_storage

def purge_expired(connection_factory, storage=None, execute=False, batch_size=100):
    storage=storage or get_attachment_storage(); limit=min(max(int(batch_size),1),1000)
    connection=connection_factory(); cursor=connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    result={"candidatos":0,"purgados":0,"falhas":0,"dry_run":not execute}
    try:
        try: quarantine_minutes=min(max(int(os.getenv("ATTACHMENT_QUARANTINE_ALERT_MINUTES","15")),1),1440)
        except ValueError: quarantine_minutes=15
        cursor.execute("""SELECT count(*) AS total FROM anexos_correcao
                          WHERE estado='ativo' AND estado_seguranca IN ('quarentena','erro_varredura')
                            AND created_at <= clock_timestamp()-(%s * interval '1 minute')""",(quarantine_minutes,))
        backlog=cursor.fetchone()["total"]
        if backlog: emit("quarantine_backlog",count=backlog,result="overdue")
        cursor.execute("""SELECT id,empresa_id,correcao_id,chave_objeto FROM anexos_correcao
            WHERE estado<>'ativo' AND purgado_at IS NULL AND retencao_ate<=clock_timestamp()
            ORDER BY retencao_ate,id LIMIT %s FOR UPDATE SKIP LOCKED""",(limit,))
        rows=cursor.fetchall(); result["candidatos"]=len(rows)
        if not execute: connection.rollback(); return result
        for row in rows:
            cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                VALUES(%s,NULL,'correcao.anexo_purge_inicio','correcao',%s,%s)""",
                (row["empresa_id"],row["correcao_id"],psycopg2.extras.Json({"anexo_id":str(row["id"]),"resultado":"iniciado"})))
            try:
                storage.delete(row["chave_objeto"])
                cursor.execute("""UPDATE anexos_correcao SET purgado_at=clock_timestamp(),
                    purge_tentativas=purge_tentativas+1,purge_erro_codigo=NULL,updated_at=clock_timestamp()
                    WHERE id=%s AND purgado_at IS NULL RETURNING id""",(row["id"],))
                if cursor.fetchone():
                    result["purgados"]+=1
                    cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                        VALUES(%s,NULL,'correcao.anexo_purgado','correcao',%s,%s)""",
                        (row["empresa_id"],row["correcao_id"],psycopg2.extras.Json({"anexo_id":str(row["id"]),"resultado":"concluido"})))
            except AttachmentStorageError:
                result["falhas"]+=1
                cursor.execute("""UPDATE anexos_correcao SET purge_tentativas=purge_tentativas+1,
                    purge_erro_codigo='storage_unavailable',updated_at=clock_timestamp() WHERE id=%s""",(row["id"],))
                cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                    VALUES(%s,NULL,'correcao.anexo_purge_falha','correcao',%s,%s)""",
                    (row["empresa_id"],row["correcao_id"],psycopg2.extras.Json({"anexo_id":str(row["id"]),"resultado":"storage_unavailable"})))
        connection.commit(); emit("purge_completed",count=result["purgados"],result="ok" if not result["falhas"] else "partial")
        return result
    except Exception: connection.rollback(); raise
    finally: cursor.close(); connection.close()
