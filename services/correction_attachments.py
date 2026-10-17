"""Domínio de comprovantes privados vinculados às correções de ponto."""

from hashlib import sha256
from datetime import timedelta
import os
import re
import unicodedata

import psycopg2.extras

from services.correction_attachment_storage import (
    AttachmentStorageError,
    AttachmentStorageNotConfigured,
    get_attachment_storage,
)
from services.management_scope import employee_scope_clause
from services.attachment_scanner import ScannerError, get_attachment_scanner
from services.attachment_observability import Timer, emit
from services.attachment_outbox import (
    asynchronous_scan_enabled,
    create_scan_job,
    requeue_scan_job,
)


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_FILENAME_CHARS = 200
ALLOWED_FILES = {
    ".pdf": ("application/pdf", "pdf"),
    ".jpg": ("image/jpeg", "jpg"),
    ".jpeg": ("image/jpeg", "jpg"),
    ".png": ("image/png", "png"),
}


class CorrectionAttachmentError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _invalid_attachment(reason, message):
    emit("upload_rejected", reason=reason)
    return CorrectionAttachmentError(message)


def normalize_filename(value):
    name = unicodedata.normalize("NFKC", str(value or ""))
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if not name:
        raise _invalid_attachment("filename", "O comprovante precisa ter um nome válido.")
    return name[:MAX_FILENAME_CHARS].rstrip(" .")


def _signature_matches(content, mime_type):
    if mime_type == "application/pdf":
        return (
            len(content) >= 12
            and content.startswith(b"%PDF-")
            and b"%%EOF" in content[-1024:]
        )
    if mime_type == "image/jpeg":
        return len(content) >= 4 and content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    if mime_type == "image/png":
        return (
            len(content) >= 33
            and content.startswith(b"\x89PNG\r\n\x1a\n")
            and content[12:16] == b"IHDR"
            and content.endswith(b"\x00\x00\x00\x00IEND\xaeB\x60\x82")
        )
    return False


def validate_attachment(file_storage):
    if file_storage is None:
        raise _invalid_attachment("missing_file", "Selecione um comprovante.")
    name = normalize_filename(file_storage.filename)
    extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in ALLOWED_FILES:
        raise _invalid_attachment("extension", "Envie um arquivo PDF, JPEG ou PNG.")
    expected_mime, canonical_extension = ALLOWED_FILES[extension]
    declared_mime = str(file_storage.content_type or "").split(";", 1)[0].strip().lower()
    if declared_mime not in {"application/pdf", "image/jpeg", "image/png"}:
        raise _invalid_attachment("mime", "O tipo MIME do comprovante não é permitido.")
    if declared_mime != expected_mime:
        raise _invalid_attachment("mime_mismatch", "A extensão e o tipo MIME do comprovante não correspondem.")
    content = file_storage.stream.read(MAX_ATTACHMENT_BYTES + 1)
    if not content:
        raise _invalid_attachment("empty", "O comprovante está vazio.")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise _invalid_attachment("size", "O comprovante deve ter no máximo 10 MiB.")
    if not _signature_matches(content, declared_mime):
        raise _invalid_attachment("signature", "O conteúdo do arquivo não corresponde ao formato informado.")
    return {
        "content": content,
        "nome_original": name,
        "tipo_mime": declared_mime,
        "extensao": canonical_extension,
        "tamanho_bytes": len(content),
        "sha256": sha256(content).hexdigest(),
    }


def serialize_attachment(row, can_mutate=False):
    situation = {
        "quarentena": "analisando", "limpo": "disponivel",
        "infectado": "bloqueado", "erro_varredura": "falha_temporaria",
    }.get(row.get("estado_seguranca", "limpo"), "bloqueado")
    return {
        "id": str(row["id"]),
        "nome": row["nome_original"],
        "tipo_mime": row["tipo_mime"],
        "tamanho_bytes": row["tamanho_bytes"],
        "sha256": row["sha256"],
        "estado": {"analisando":"Analisando","disponivel":"Disponível","bloqueado":"Bloqueado","falha_temporaria":"Falha temporária"}[situation],
        "estado_historico": row["estado"],
        "estado_seguranca": row.get("estado_seguranca", "limpo"),
        "situacao": situation,
        "criado_em": row["created_at"].isoformat(),
        "pode_alterar": bool(can_mutate),
    }


def _audit(cursor, auth_context, correction, attachment, action):
    metadata = {
        "correcao_id": str(correction["id"]),
        "anexo_id": str(attachment["id"]),
        "empresa_id": str(auth_context["empresa_id"]),
        "funcionario_id": str(correction["funcionario_id"]),
        "papel": auth_context["perfil"],
        "tamanho_bytes": attachment["tamanho_bytes"],
        "tipo_mime": attachment["tipo_mime"],
        "sha256": attachment["sha256"],
        "estado": attachment["estado"],
        "estado_seguranca": attachment.get("estado_seguranca"),
    }
    cursor.execute(
        """INSERT INTO auditoria
           (empresa_id, ator_usuario_id, acao, entidade_tipo, entidade_id, metadados)
           VALUES (%s, %s, %s, 'correcao', %s, %s)""",
        (
            auth_context["empresa_id"],
            auth_context["user_id"],
            action,
            correction["id"],
            psycopg2.extras.Json(metadata),
        ),
    )


def _locked_owned_correction(cursor, auth_context, correction_id):
    cursor.execute(
        """SELECT c.id, c.empresa_id, c.funcionario_id, c.estado
           FROM correcoes c
           WHERE c.id=%s AND c.empresa_id=%s AND c.funcionario_id=%s
             AND c.solicitante_usuario_id=%s
           FOR UPDATE""",
        (
            correction_id,
            auth_context["empresa_id"],
            auth_context["funcionario_id"],
            auth_context["user_id"],
        ),
    )
    row = cursor.fetchone()
    if not row:
        raise CorrectionAttachmentError("Ocorrência não encontrada.", 404)
    return row


def _visible_correction(cursor, auth_context, correction_id, management, lock=False):
    conditions = ["c.id=%s", "c.empresa_id=%s"]
    params = [correction_id, auth_context["empresa_id"]]
    if management:
        scope, scope_params = employee_scope_clause(auth_context, "f")
        conditions.append("(" + scope + ")")
        params.extend(scope_params)
    else:
        conditions.extend(["c.funcionario_id=%s", "c.solicitante_usuario_id=%s"])
        params.extend([auth_context["funcionario_id"], auth_context["user_id"]])
    cursor.execute(
        """SELECT c.id, c.empresa_id, c.funcionario_id, c.estado
           FROM correcoes c
           INNER JOIN funcionarios f
             ON f.id=c.funcionario_id AND f.empresa_id=c.empresa_id
           WHERE """
        + " AND ".join(conditions)
        + (" FOR UPDATE OF c" if lock else ""),
        tuple(params),
    )
    row = cursor.fetchone()
    if not row:
        raise CorrectionAttachmentError("Ocorrência não encontrada.", 404)
    return row


def _active_attachment(cursor, company_id, correction_id, lock=False):
    cursor.execute(
        """SELECT * FROM anexos_correcao
           WHERE empresa_id=%s AND correcao_id=%s AND estado='ativo'
           ORDER BY created_at DESC, id DESC LIMIT 1"""
        + (" FOR UPDATE" if lock else ""),
        (company_id, correction_id),
    )
    return cursor.fetchone()


def _insert_validated(cursor, auth_context, correction, validated, storage):
    key = storage.generate_key(validated["extensao"], auth_context["empresa_id"], "quarantine")
    storage.put(key, validated["content"], validated["tipo_mime"], validated["sha256"])
    try:
        current = _active_attachment(
            cursor, auth_context["empresa_id"], correction["id"], lock=True
        )
        if current:
            cursor.execute(
                """UPDATE anexos_correcao
                   SET estado='substituido',
                       retencao_ate=COALESCE(retencao_ate, clock_timestamp() + (%s * interval '1 day')),
                       updated_at=clock_timestamp()
                   WHERE id=%s""",
                (_retention_days(), current["id"]),
            )
        cursor.execute(
            """INSERT INTO anexos_correcao
               (empresa_id, correcao_id, funcionario_id, enviado_por_usuario_id,
                chave_objeto, nome_original, tipo_mime, tamanho_bytes, sha256)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (
                auth_context["empresa_id"],
                correction["id"],
                correction["funcionario_id"],
                auth_context["user_id"],
                key,
                validated["nome_original"],
                validated["tipo_mime"],
                validated["tamanho_bytes"],
                validated["sha256"],
            ),
        )
        created = cursor.fetchone()
        if asynchronous_scan_enabled():
            create_scan_job(cursor, auth_context["empresa_id"], created["id"])
        _audit(
            cursor,
            auth_context,
            correction,
            created,
            "correcao.anexo_substituido" if current else "correcao.anexo_incluido",
        )
        return created, key
    except Exception:
        storage.delete(key)
        raise


def attach_to_new_correction(cursor, auth_context, correction, validated, storage=None):
    """Anexa durante a mesma transação usada para criar a correção."""
    try:
        storage = storage or get_attachment_storage()
    except AttachmentStorageNotConfigured as exc:
        raise CorrectionAttachmentError(str(exc), 503) from exc
    created, key = _insert_validated(cursor, auth_context, correction, validated, storage)
    return created, key, storage


def upload_attachment(connection_factory, auth_context, correction_id, file_storage, storage=None):
    validated = validate_attachment(file_storage)
    try:
        storage = storage or get_attachment_storage()
    except AttachmentStorageNotConfigured as exc:
        raise CorrectionAttachmentError(str(exc), 503) from exc
    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    key = None
    try:
        correction = _locked_owned_correction(cursor, auth_context, correction_id)
        if correction["estado"] != "pendente_gestor":
            raise CorrectionAttachmentError(
                "O comprovante só pode ser alterado enquanto a solicitação está pendente com o gestor.",
                409,
            )
        created, key = _insert_validated(cursor, auth_context, correction, validated, storage)
        async_scan = asynchronous_scan_enabled()
        connection.commit()
        result = created
        if not async_scan:
            result = scan_attachment(connection_factory, auth_context, created["id"], storage=storage)
        emit("upload_accepted", attachment_id=str(created["id"]), result=result.get("estado_seguranca"))
        return result
    except CorrectionAttachmentError:
        connection.rollback()
        raise
    except (AttachmentStorageError, AttachmentStorageNotConfigured) as exc:
        connection.rollback()
        emit("storage_failed", company_id=str(auth_context["empresa_id"]), reason="upload")
        raise CorrectionAttachmentError(str(exc), 503) from exc
    except Exception:
        connection.rollback()
        if key:
            storage.delete(key)
        raise
    finally:
        cursor.close()
        connection.close()


def get_attachment(connection_factory, auth_context, correction_id, management=False):
    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        correction = _visible_correction(cursor, auth_context, correction_id, management)
        attachment = _active_attachment(cursor, auth_context["empresa_id"], correction_id)
        if not attachment:
            raise CorrectionAttachmentError("Comprovante não encontrado.", 404)
        can_mutate = not management and correction["estado"] == "pendente_gestor"
        return correction, attachment, can_mutate
    finally:
        cursor.close()
        connection.close()


def download_attachment(
    connection_factory, auth_context, correction_id, management=False, storage=None
):
    try:
        storage = storage or get_attachment_storage()
    except AttachmentStorageNotConfigured as exc:
        raise CorrectionAttachmentError(str(exc), 503) from exc
    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        correction = _visible_correction(cursor, auth_context, correction_id, management)
        attachment = _active_attachment(cursor, auth_context["empresa_id"], correction_id)
        if not attachment:
            raise CorrectionAttachmentError("Comprovante não encontrado.", 404)
        if attachment.get("estado_seguranca") != "limpo":
            emit("download_denied", attachment_id=str(attachment["id"]), company_id=str(auth_context["empresa_id"]), reason="security_state")
            raise CorrectionAttachmentError("Comprovante ainda não está disponível para download.", 423)
        content = storage.read(attachment["chave_objeto"], attachment["tamanho_bytes"], attachment["sha256"])
        if management:
            _audit(cursor, auth_context, correction, attachment, "correcao.anexo_download_gestao")
            connection.commit()
        emit("download_authorized", attachment_id=str(attachment["id"]), company_id=str(auth_context["empresa_id"]), result="allowed")
        return attachment, content
    except AttachmentStorageError as exc:
        connection.rollback()
        emit("storage_failed", company_id=str(auth_context["empresa_id"]), reason="download")
        raise CorrectionAttachmentError(str(exc), 503) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def remove_attachment(connection_factory, auth_context, correction_id):
    connection = connection_factory()
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        correction = _locked_owned_correction(cursor, auth_context, correction_id)
        if correction["estado"] != "pendente_gestor":
            raise CorrectionAttachmentError(
                "O comprovante só pode ser removido enquanto a solicitação está pendente com o gestor.",
                409,
            )
        attachment = _active_attachment(
            cursor, auth_context["empresa_id"], correction_id, lock=True
        )
        if not attachment:
            raise CorrectionAttachmentError("Comprovante não encontrado.", 404)
        cursor.execute(
            """UPDATE anexos_correcao
               SET estado='removido', removed_at=clock_timestamp(),
                   retencao_ate=COALESCE(retencao_ate, clock_timestamp() + (%s * interval '1 day')),
                   updated_at=clock_timestamp()
               WHERE id=%s RETURNING *""",
            (_retention_days(), attachment["id"]),
        )
        removed = cursor.fetchone()
        _audit(cursor, auth_context, correction, removed, "correcao.anexo_removido")
        connection.commit()
        return removed
    except CorrectionAttachmentError:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

def _retention_days(infected=False):
    name = "ATTACHMENT_INFECTED_RETENTION_DAYS" if infected else "ATTACHMENT_RETENTION_DAYS"
    default = 30 if infected else 90
    try: value = int(os.getenv(name, str(default)))
    except ValueError: value = default
    return min(max(value, 1), 3650)


def request_scan_retry(connection_factory, auth_context, attachment_id, management=False):
    connection=connection_factory(); cursor=connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""SELECT a.*,c.id AS correction_id,c.funcionario_id
                          FROM anexos_correcao a
                          JOIN correcoes c ON c.id=a.correcao_id AND c.empresa_id=a.empresa_id
                          JOIN funcionarios f ON f.id=c.funcionario_id AND f.empresa_id=c.empresa_id
                          WHERE a.id=%s AND a.empresa_id=%s FOR UPDATE OF a""",
                       (attachment_id,auth_context["empresa_id"]))
        attachment=cursor.fetchone()
        if not attachment: raise CorrectionAttachmentError("Comprovante não encontrado.",404)
        if management:
            scope,params=employee_scope_clause(auth_context,"f")
            cursor.execute("SELECT 1 FROM funcionarios f WHERE f.id=%s AND f.empresa_id=%s AND ("+scope+")",
                           (attachment["funcionario_id"],auth_context["empresa_id"],*params))
            if not cursor.fetchone(): raise CorrectionAttachmentError("Comprovante não encontrado.",404)
        if attachment["estado"]!="ativo" or attachment["estado_seguranca"] not in {"quarentena","erro_varredura"}:
            raise CorrectionAttachmentError("O comprovante não pode ser reenviado para análise.",409)
        requeue_scan_job(cursor,auth_context["empresa_id"],attachment_id)
        _audit(cursor,auth_context,{"id":attachment["correction_id"],"funcionario_id":attachment["funcionario_id"]},attachment,"correcao.anexo_varredura_retry_solicitado")
        connection.commit()
        emit("scan_retry_requested",attachment_id=str(attachment_id),result="pending")
        return attachment
    except Exception:
        connection.rollback(); raise
    finally:
        cursor.close(); connection.close()

def scan_attachment(connection_factory, auth_context, attachment_id, storage=None, scanner=None, management=False):
    storage = storage or get_attachment_storage()
    scanner_error = None
    if scanner is None:
        try: scanner = get_attachment_scanner()
        except ScannerError as exc: scanner_error = exc
    connection = connection_factory(); cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    promotion = None
    try:
        cursor.execute("""SELECT a.*, c.id AS correction_id, c.funcionario_id
                          FROM anexos_correcao a JOIN correcoes c ON c.id=a.correcao_id AND c.empresa_id=a.empresa_id
                          JOIN funcionarios f ON f.id=c.funcionario_id AND f.empresa_id=c.empresa_id
                          WHERE a.id=%s AND a.empresa_id=%s FOR UPDATE OF a""",
                       (attachment_id, auth_context["empresa_id"]))
        attachment=cursor.fetchone()
        if not attachment: raise CorrectionAttachmentError("Comprovante não encontrado.",404)
        if management:
            scope, params=employee_scope_clause(auth_context,"f")
            cursor.execute("SELECT 1 FROM funcionarios f WHERE f.id=%s AND f.empresa_id=%s AND ("+scope+")",
                           (attachment["funcionario_id"],auth_context["empresa_id"],*params))
            if not cursor.fetchone(): raise CorrectionAttachmentError("Comprovante não encontrado.",404)
        if attachment["estado_seguranca"] not in {"quarentena","erro_varredura"}: return attachment
        is_retry=attachment["estado_seguranca"]=="erro_varredura"
        cursor.execute("UPDATE anexos_correcao SET scan_tentativas=scan_tentativas+1,scan_iniciado_at=clock_timestamp(),estado_seguranca='quarentena' WHERE id=%s",(attachment_id,))
        content=storage.read(attachment["chave_objeto"],attachment["tamanho_bytes"],attachment["sha256"])
        try:
            if scanner_error: raise scanner_error
            with Timer() as timer: result=scanner.scan(content)
            if result.status not in {"limpo","infectado"}: raise ScannerError("Estado desconhecido.")
            new_key=attachment["chave_objeto"]
            retention=None
            if result.status=="limpo":
                new_key=storage.promote(attachment["chave_objeto"]); promotion=(new_key,attachment["chave_objeto"])
            else: retention=f"{_retention_days(True)} days"
            cursor.execute("""UPDATE anexos_correcao SET estado_seguranca=%s,chave_objeto=%s,
                scan_concluido_at=clock_timestamp(),scan_resultado_codigo=%s,
                retencao_ate=CASE WHEN %s IS NULL THEN retencao_ate ELSE clock_timestamp()+(%s::interval) END,
                updated_at=clock_timestamp() WHERE id=%s RETURNING *""",
                (result.status,new_key,result.code,retention,retention,attachment_id))
            updated=cursor.fetchone(); _audit(cursor,auth_context,{"id":attachment["correction_id"],"funcionario_id":attachment["funcionario_id"]},updated,"correcao.anexo_varredura_retry" if is_retry else "correcao.anexo_varredura")
            connection.commit(); emit("scan_completed",attachment_id=str(attachment_id),company_id=str(auth_context["empresa_id"]),result=result.status,duration_ms=timer.duration_ms)
            return updated
        except (ScannerError, AttachmentStorageError):
            cursor.execute("""UPDATE anexos_correcao SET estado_seguranca='erro_varredura',scan_concluido_at=clock_timestamp(),scan_resultado_codigo='scan_unavailable',updated_at=clock_timestamp() WHERE id=%s RETURNING *""",(attachment_id,))
            updated=cursor.fetchone(); _audit(cursor,auth_context,{"id":attachment["correction_id"],"funcionario_id":attachment["funcionario_id"]},updated,"correcao.anexo_varredura_erro")
            connection.commit(); emit("scan_failed",attachment_id=str(attachment_id),company_id=str(auth_context["empresa_id"]),reason="dependency_unavailable")
            return updated
    except CorrectionAttachmentError: connection.rollback(); raise
    except Exception:
        connection.rollback()
        if promotion:
            try: storage.restore_promotion(*promotion)
            except AttachmentStorageError:
                emit("storage_failed",attachment_id=str(attachment_id),company_id=str(auth_context["empresa_id"]),reason="promotion_compensation")
        raise
    finally: cursor.close(); connection.close()
