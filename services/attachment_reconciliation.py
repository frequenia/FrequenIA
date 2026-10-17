"""Reconciliação dry-run entre PostgreSQL, outbox e armazenamento privado."""

from collections import Counter
from hashlib import sha256

import psycopg2.extras

from services.attachment_observability import emit, metric
from services.attachment_outbox import create_scan_job
from services.correction_attachment_storage import AttachmentStorageError, get_attachment_storage


def _opaque_key_id(key):
    return sha256(str(key).encode("utf-8")).hexdigest()[:16]


def reconcile_attachments(connection_factory, storage=None, company_id=None, batch_size=100, after_id=None,
                          repair=None, execute=False):
    if repair and not execute:
        raise ValueError("Reparo exige --execute explícito.")
    if repair not in {None,"requeue-missing-job"}:
        raise ValueError("Operação de reparo não permitida.")
    if repair and not company_id:
        raise ValueError("Reparo exige empresa explícita.")
    storage=storage or get_attachment_storage()
    limit=min(max(int(batch_size),1),500)
    connection=connection_factory(); cursor=connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    findings=[]; known_keys=set(); last_id=after_id
    try:
        conditions=[]; params=[]
        if company_id: conditions.append("a.empresa_id=%s"); params.append(company_id)
        if after_id: conditions.append("a.id>%s"); params.append(after_id)
        where="WHERE "+" AND ".join(conditions) if conditions else ""
        cursor.execute("""SELECT a.*,j.id AS job_id,j.estado AS job_estado
                          FROM anexos_correcao a LEFT JOIN anexo_varredura_jobs j ON j.anexo_id=a.id
                          %s ORDER BY a.id LIMIT %%s""" % where,(*params,limit))
        rows=cursor.fetchall()
        for row in rows:
            last_id=str(row["id"]); known_keys.add(row["chave_objeto"])
            if row["purgado_at"] is None:
                try:
                    storage.read(row["chave_objeto"],row["tamanho_bytes"],row["sha256"])
                except AttachmentStorageError as exc:
                    reason="metadata_without_object" if "indisponível" in str(exc) else "integrity_mismatch"
                    findings.append({"type":reason,"attachment_id":str(row["id"])})
            if row["estado"]=="ativo" and row["estado_seguranca"] in {"quarentena","erro_varredura"} and row["job_estado"] not in {"pendente_publicacao","publicado","processando","falha_reprocessavel"}:
                findings.append({"type":"quarantine_without_active_job","attachment_id":str(row["id"])})
                if repair=="requeue-missing-job": create_scan_job(cursor,row["empresa_id"],row["id"])
            if row["job_estado"]=="concluido" and row["estado_seguranca"] not in {"limpo","infectado"}:
                findings.append({"type":"completed_job_nonterminal_attachment","attachment_id":str(row["id"])})
            if row["estado_seguranca"]=="limpo" and "/clean/" not in row["chave_objeto"] and not row["chave_objeto"].startswith("correcoes/"):
                findings.append({"type":"clean_wrong_prefix","attachment_id":str(row["id"])})
            if row["purgado_at"] is not None:
                try:
                    storage.read(row["chave_objeto"])
                    findings.append({"type":"purged_object_present","attachment_id":str(row["id"])})
                except AttachmentStorageError:
                    pass
        if company_id:
            prefix=f"{__import__('os').getenv('APP_ENV','development').strip().lower()}/{company_id}/"
            cursor.execute("SELECT chave_objeto FROM anexos_correcao WHERE empresa_id=%s",(company_id,))
            all_known={item["chave_objeto"] for item in cursor.fetchall()}
            for key in storage.list_keys(prefix):
                if key not in all_known:
                    findings.append({"type":"object_without_metadata","object_id":_opaque_key_id(key)})
        if execute and repair:
            cursor.execute("""INSERT INTO auditoria(empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
                              VALUES(%s,NULL,'correcao.anexo_reconciliacao_reparo','empresa',%s,%s)""",
                           (company_id,company_id,psycopg2.extras.Json({"operacao":repair,"quantidade":len(findings)})))
            connection.commit()
        else:
            connection.rollback()
    finally:
        cursor.close(); connection.close()
    counts=dict(Counter(item["type"] for item in findings))
    emit("reconciliation_completed",count=len(findings),result="repaired" if execute else "dry_run")
    metric("ReconciliationDivergences",len(findings),process="reconciliation",result="found" if findings else "clean")
    metric("QuarantineDelayed",counts.get("quarantine_without_active_job",0),process="reconciliation",result="observed")
    return {"dry_run":not execute,"counts":counts,"findings":findings,"next_after_id":last_id,"has_more":len(rows)==limit}
