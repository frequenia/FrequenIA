"""Outbox pós-commit para a tag purge-eligible, com PostgreSQL como autoridade."""
import psycopg2.extras
from services.attachment_observability import emit,metric
from services.correction_attachment_storage import AttachmentStorageError,get_attachment_storage

def authorize_expired(connection_factory,batch_size=100,execute=False):
    limit=min(max(int(batch_size),1),500); connection=connection_factory()
    cursor=connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    result={"dry_run":not execute,"candidates":0,"authorized":0}
    try:
        cursor.execute("""SELECT id,empresa_id FROM anexos_correcao
            WHERE estado<>'ativo' AND estado_seguranca IN ('limpo','infectado')
              AND purgado_at IS NULL AND retencao_ate<=clock_timestamp()
              AND (preservacao_ate IS NULL OR preservacao_ate<=clock_timestamp())
            ORDER BY retencao_ate,id LIMIT %s FOR UPDATE SKIP LOCKED""",(limit,))
        rows=cursor.fetchall(); result["candidates"]=len(rows)
        if not execute: connection.rollback(); return result
        for row in rows:
            cursor.execute("UPDATE anexos_correcao SET purge_autorizado_at=coalesce(purge_autorizado_at,clock_timestamp()),updated_at=clock_timestamp() WHERE id=%s",(row["id"],))
            cursor.execute("""INSERT INTO anexo_purge_tag_jobs(empresa_id,anexo_id) VALUES(%s,%s)
                ON CONFLICT(anexo_id) DO UPDATE SET estado=CASE WHEN anexo_purge_tag_jobs.estado='aplicado' THEN 'aplicado' ELSE 'pendente' END,
                proxima_tentativa_at=clock_timestamp(),updated_at=clock_timestamp()""",(row["empresa_id"],row["id"]))
            cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                VALUES(%s,NULL,'anexo.purge_tag_autorizada','anexo_correcao',%s,%s)""",
                (row["empresa_id"],row["id"],psycopg2.extras.Json({"anexo_id":str(row["id"]),"resultado":"autorizado"})))
            result["authorized"]+=1
        connection.commit()
        metric("PurgeEligibilityAuthorized",result["authorized"],process="purge-tagging",result="committed")
        return result
    except Exception: connection.rollback(); raise
    finally: cursor.close(); connection.close()

def apply_authorized_tags(connection_factory,storage=None,batch_size=100,execute=False):
    storage=storage or get_attachment_storage(); limit=min(max(int(batch_size),1),500)
    connection=connection_factory(); cursor=connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    result={"dry_run":not execute,"candidates":0,"tagged":0,"failed":0}
    try:
        cursor.execute("""SELECT j.*,a.chave_objeto,a.tamanho_bytes,a.sha256,a.estado,a.estado_seguranca,
                                 a.retencao_ate,a.preservacao_ate,a.purge_autorizado_at,a.purgado_at,
                                 a.retencao_ate<=clock_timestamp() AS retencao_vencida,
                                 (a.preservacao_ate IS NULL OR a.preservacao_ate<=clock_timestamp()) AS preservacao_liberada
            FROM anexo_purge_tag_jobs j JOIN anexos_correcao a ON a.id=j.anexo_id AND a.empresa_id=j.empresa_id
            WHERE j.estado IN ('pendente','falha_reprocessavel') AND j.proxima_tentativa_at<=clock_timestamp()
            ORDER BY j.proxima_tentativa_at,j.id LIMIT %s FOR UPDATE OF j SKIP LOCKED""",(limit,))
        rows=cursor.fetchall(); result["candidates"]=len(rows)
        if not execute: connection.rollback(); return result
        for row in rows:
            eligible=(row["estado"]!="ativo" and row["estado_seguranca"] in {"limpo","infectado"} and row["purgado_at"] is None
                and row["purge_autorizado_at"] is not None and row["retencao_ate"] is not None
                and row["retencao_vencida"] and row["preservacao_liberada"])
            if not eligible:
                cursor.execute("UPDATE anexo_purge_tag_jobs SET estado='cancelado',erro_codigo='not_eligible',updated_at=clock_timestamp() WHERE id=%s",(row["id"],)); continue
            try:
                storage.read(row["chave_objeto"],row["tamanho_bytes"],row["sha256"])
                storage.tag_purge_eligible(row["chave_objeto"])
                cursor.execute("UPDATE anexo_purge_tag_jobs SET estado='aplicado',tentativas=tentativas+1,aplicado_at=clock_timestamp(),erro_codigo=NULL,updated_at=clock_timestamp() WHERE id=%s",(row["id"],))
                cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                    VALUES(%s,NULL,'anexo.purge_tag_aplicada','anexo_correcao',%s,%s)""",
                    (row["empresa_id"],row["anexo_id"],psycopg2.extras.Json({"job_id":str(row["id"]),"resultado":"aplicado"})))
                result["tagged"]+=1
            except AttachmentStorageError:
                cursor.execute("UPDATE anexo_purge_tag_jobs SET estado='falha_reprocessavel',tentativas=tentativas+1,erro_codigo='storage_unavailable',proxima_tentativa_at=clock_timestamp()+interval '30 seconds',updated_at=clock_timestamp() WHERE id=%s",(row["id"],))
                cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                    VALUES(%s,NULL,'anexo.purge_tag_falhou','anexo_correcao',%s,%s)""",
                    (row["empresa_id"],row["anexo_id"],psycopg2.extras.Json({"job_id":str(row["id"]),"resultado":"storage_unavailable"})))
                result["failed"]+=1
        connection.commit()
        emit("purge_tagging_completed",count=result["tagged"],result="partial" if result["failed"] else "ok")
        metric("PurgeEligibilityTagged",result["tagged"],process="purge-tagging",result="success")
        metric("PurgeEligibilityFailures",result["failed"],process="purge-tagging",result="error")
        return result
    except Exception: connection.rollback(); raise
    finally: cursor.close(); connection.close()
