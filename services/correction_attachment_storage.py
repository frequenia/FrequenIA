"""Adaptadores privados de armazenamento para comprovantes de correção."""
from hashlib import sha256
from pathlib import Path
import os
import re
from uuid import UUID, uuid4

OBJECT_KEY_RE = re.compile(r"^[a-z0-9-]{1,32}/[0-9a-f-]{36}/(quarantine|clean)/[0-9a-f-]{36}\.(pdf|jpg|png)$")
LEGACY_KEY_RE = re.compile(r"^correcoes/[0-9a-f-]{36}\.(pdf|jpg|png)$")

class AttachmentStorageError(Exception): pass
class AttachmentStorageNotConfigured(AttachmentStorageError): pass

def _environment():
    value = os.getenv("APP_ENV", "development").strip().lower()
    return value if re.fullmatch(r"[a-z0-9-]{1,32}", value) else "development"

def _company_segment(company_id):
    try: return str(UUID(str(company_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AttachmentStorageError("Empresa da chave de objeto é inválida.") from exc

def _new_key(extension, company_id, area="quarantine"):
    if extension not in {"pdf", "jpg", "png"} or area not in {"quarantine", "clean"}:
        raise AttachmentStorageError("Parâmetros da chave de objeto são inválidos.")
    return f"{_environment()}/{_company_segment(company_id)}/{area}/{uuid4()}.{extension}"

def _validate_key(key):
    value = str(key or "")
    if not (OBJECT_KEY_RE.fullmatch(value) or LEGACY_KEY_RE.fullmatch(value)):
        raise AttachmentStorageError("Chave de objeto inválida.")
    return value

def _verify_content(content, expected_size, expected_sha256):
    if expected_size is not None and len(content) != int(expected_size):
        raise AttachmentStorageError("Tamanho do objeto privado divergente.")
    if expected_sha256 and sha256(content).hexdigest() != expected_sha256:
        raise AttachmentStorageError("Checksum do objeto privado divergente.")

class LocalPrivateAttachmentStorage:
    """Backend privado restrito a desenvolvimento e testes."""
    def __init__(self, root):
        if _environment() not in {"development", "test", "testing"}:
            raise AttachmentStorageNotConfigured("Armazenamento local não é permitido neste ambiente.")
        value = str(root or "").strip()
        if not value: raise AttachmentStorageNotConfigured("Armazenamento privado não configurado.")
        self.root = Path(value).expanduser().resolve()
        public_root = (Path(__file__).resolve().parents[1] / "static").resolve()
        if self.root == public_root or public_root in self.root.parents:
            raise AttachmentStorageNotConfigured("Armazenamento não pode ficar no diretório público.")
        self.root.mkdir(parents=True, exist_ok=True)
        self._purge_tags=set()

    def generate_key(self, extension, company_id=None, area="quarantine"):
        return _new_key(extension, company_id, area)
    def _path(self, key):
        target = (self.root / _validate_key(key)).resolve()
        if self.root not in target.parents: raise AttachmentStorageError("Chave inválida.")
        return target
    def put(self, key, content, mime_type=None, checksum=None):
        target = self._path(key); target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise AttachmentStorageError("Falha no armazenamento privado.") from exc
    def read(self, key, expected_size=None, expected_sha256=None):
        try: content = self._path(key).read_bytes()
        except (OSError, AttachmentStorageError) as exc: raise AttachmentStorageError("Objeto privado indisponível.") from exc
        _verify_content(content, expected_size, expected_sha256); return content
    def promote(self, key):
        source = self._path(key); parts = _validate_key(key).split("/")
        promoted = self.generate_key(source.suffix.lstrip("."), parts[1] if len(parts)==4 else None, "clean")
        target = self._path(promoted); target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open("rb") as origin, target.open("xb") as destination:
                for chunk in iter(lambda: origin.read(65536), b""):
                    destination.write(chunk)
                destination.flush(); os.fsync(destination.fileno())
            source.unlink()
        except OSError as exc:
            target.unlink(missing_ok=True)
            raise AttachmentStorageError("Falha ao promover objeto limpo.") from exc
        return promoted
    def restore_promotion(self, promoted_key, quarantine_key):
        source=self._path(promoted_key); target=self._path(quarantine_key); target.parent.mkdir(parents=True,exist_ok=True)
        try:
            with source.open("rb") as origin, target.open("xb") as destination:
                for chunk in iter(lambda: origin.read(65536), b""):
                    destination.write(chunk)
                destination.flush(); os.fsync(destination.fileno())
            source.unlink()
        except OSError as exc:
            target.unlink(missing_ok=True)
            raise AttachmentStorageError("Falha ao compensar promoção do objeto.") from exc
    def delete(self, key):
        try: self._path(key).unlink(missing_ok=True)
        except (OSError, AttachmentStorageError) as exc: raise AttachmentStorageError("Falha ao remover objeto privado.") from exc
    def healthcheck(self): return self.root.is_dir() and os.access(self.root, os.R_OK | os.W_OK)
    def list_keys(self, prefix=""):
        base=(self.root / prefix).resolve() if prefix else self.root
        if base != self.root and self.root not in base.parents:
            raise AttachmentStorageError("Prefixo inválido.")
        if not base.exists(): return iter(())
        def iterator():
            for item in base.rglob("*"):
                if item.is_file():
                    yield item.relative_to(self.root).as_posix()
        return iterator()
    def tag_purge_eligible(self,key):
        target=self._path(key)
        if not target.is_file(): raise AttachmentStorageError("Objeto privado indisponível.")
        self._purge_tags.add(_validate_key(key))
    def is_purge_eligible(self,key):
        self._path(key)
        return _validate_key(key) in self._purge_tags

class S3PrivateAttachmentStorage:
    """S3 privado com SDK oficial, SSE e validação integral na leitura."""
    def __init__(self, bucket, region, endpoint_url=None, client=None):
        self.bucket, self.region = str(bucket or "").strip(), str(region or "").strip()
        endpoint = str(endpoint_url or "").strip() or None
        if not self.bucket or not self.region: raise AttachmentStorageNotConfigured("Configuração S3 incompleta.")
        if endpoint and not endpoint.startswith("https://") and _environment() not in {"test", "testing"}:
            raise AttachmentStorageNotConfigured("O endpoint S3 deve usar TLS.")
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", region_name=self.region, endpoint_url=endpoint,
                config=Config(connect_timeout=3, read_timeout=10,
                    retries={"total_max_attempts":3,"mode":"standard"}, s3={"addressing_style":"path"}))
        self.client = client
    def generate_key(self, extension, company_id=None, area="quarantine"): return _new_key(extension, company_id, area)
    def put(self, key, content, mime_type=None, checksum=None):
        try: self.client.put_object(Bucket=self.bucket, Key=_validate_key(key), Body=content,
            ContentType=mime_type or "application/octet-stream", ServerSideEncryption="AES256",
            Metadata={"sha256":checksum or sha256(content).hexdigest(),"length":str(len(content))})
        except Exception as exc: raise AttachmentStorageError("Falha no armazenamento privado.") from exc
    def read(self, key, expected_size=None, expected_sha256=None):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_validate_key(key)); body=response["Body"]
            try: content=body.read()
            finally: body.close()
        except Exception as exc: raise AttachmentStorageError("Objeto privado indisponível.") from exc
        metadata=response.get("Metadata", {})
        if response.get("ContentLength") != len(content) or metadata.get("length") != str(len(content)) or metadata.get("sha256") != sha256(content).hexdigest():
            raise AttachmentStorageError("Metadados do objeto privado divergentes.")
        _verify_content(content, expected_size, expected_sha256); return content
    def promote(self, key):
        key=_validate_key(key); parts=key.split("/"); promoted=self.generate_key(key.rsplit(".",1)[-1],parts[1],"clean")
        try:
            self.client.copy_object(Bucket=self.bucket,Key=promoted,CopySource={"Bucket":self.bucket,"Key":key},ServerSideEncryption="AES256",MetadataDirective="COPY")
            self.client.delete_object(Bucket=self.bucket,Key=key)
        except Exception as exc: raise AttachmentStorageError("Falha ao promover objeto limpo.") from exc
        return promoted
    def restore_promotion(self,promoted_key,quarantine_key):
        promoted_key=_validate_key(promoted_key); quarantine_key=_validate_key(quarantine_key)
        try:
            self.client.copy_object(Bucket=self.bucket,Key=quarantine_key,CopySource={"Bucket":self.bucket,"Key":promoted_key},ServerSideEncryption="AES256",MetadataDirective="COPY")
            self.client.delete_object(Bucket=self.bucket,Key=promoted_key)
        except Exception as exc: raise AttachmentStorageError("Falha ao compensar promoção do objeto.") from exc
    def delete(self,key):
        try: self.client.delete_object(Bucket=self.bucket,Key=_validate_key(key))
        except Exception as exc: raise AttachmentStorageError("Falha ao remover objeto privado.") from exc
    def healthcheck(self):
        try:
            self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f"{_environment()}/",
                MaxKeys=1,
            )
            return True
        except Exception: return False
    def list_keys(self,prefix=""):
        safe_prefix=str(prefix or "")
        if safe_prefix and not re.fullmatch(r"[a-z0-9-]{1,32}/(?:[0-9a-f-]{36}/)?",safe_prefix):
            raise AttachmentStorageError("Prefixo inválido.")
        try:
            paginator=self.client.get_paginator("list_objects_v2")
            pages=paginator.paginate(Bucket=self.bucket,Prefix=safe_prefix)
            return (item["Key"] for page in pages for item in page.get("Contents",[]))
        except Exception as exc: raise AttachmentStorageError("Falha ao listar objetos privados.") from exc
    def tag_purge_eligible(self,key):
        try:
            self.client.put_object_tagging(Bucket=self.bucket,Key=_validate_key(key),Tagging={"TagSet":[{"Key":"frequenia-purge-eligible","Value":"true"}]})
        except Exception as exc: raise AttachmentStorageError("Falha ao marcar elegibilidade de purga.") from exc
    def is_purge_eligible(self,key):
        try:
            response=self.client.get_object_tagging(Bucket=self.bucket,Key=_validate_key(key))
            return any(item.get("Key")=="frequenia-purge-eligible" and item.get("Value")=="true" for item in response.get("TagSet",[]))
        except Exception as exc: raise AttachmentStorageError("Falha ao consultar elegibilidade de purga.") from exc

def get_attachment_storage():
    provider=os.getenv("ATTACHMENT_STORAGE_PROVIDER","local").strip().lower()
    if _environment() in {"production","prod"} and provider != "s3": raise AttachmentStorageNotConfigured("Produção exige armazenamento S3 privado.")
    if provider=="local": return LocalPrivateAttachmentStorage(os.getenv("ATTACHMENT_STORAGE_ROOT"))
    if provider=="s3": return S3PrivateAttachmentStorage(os.getenv("ATTACHMENT_S3_BUCKET"),os.getenv("ATTACHMENT_S3_REGION"),os.getenv("ATTACHMENT_S3_ENDPOINT_URL"))
    raise AttachmentStorageNotConfigured("Provedor de armazenamento inválido.")
