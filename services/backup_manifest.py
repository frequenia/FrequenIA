"""Manifesto versionado e fail-closed para conjuntos sintéticos de continuidade."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import UUID,uuid4

MANIFEST_VERSION=1
REQUIRED={"schema_version","set_id","logical_environment","created_at","components","migrations","item_count","total_bytes","artifacts","encryption","verification","rpo_seconds","rto_seconds","complete"}
ARTIFACT_KEYS={"artifact_id","component","relative_path","size","sha256"}
FORBIDDEN=re.compile(r"(cpf|matricula|e-?mail|token|secret|password|credential|signed.?url|object.?key|chave_objeto|conteudo)",re.I)

class ManifestError(ValueError): pass

def canonical_json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def file_sha256(path):
    digest=sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(65536),b""): digest.update(chunk)
    return digest.hexdigest()

def build_manifest(artifacts,environment,migrations,policy,encryption="test-ephemeral-aes256",now=None,set_id=None):
    now=now or datetime.now(timezone.utc); set_id=str(UUID(str(set_id or uuid4())))
    entries=[]
    for artifact in artifacts:
        path=Path(artifact["path"]); relative=str(artifact["relative_path"])
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not re.fullmatch(r"[a-z0-9_.-]{1,128}",relative):
            raise ManifestError("Caminho técnico do artefato inválido.")
        entries.append({"artifact_id":str(uuid4()),"component":artifact["component"],"relative_path":relative,"size":path.stat().st_size,"sha256":file_sha256(path)})
    manifest={
        "schema_version":MANIFEST_VERSION,"set_id":set_id,"logical_environment":str(environment),
        "created_at":now.astimezone(timezone.utc).isoformat(),"components":sorted({e["component"] for e in entries}),
        "migrations":list(migrations),"item_count":len(entries),"total_bytes":sum(e["size"] for e in entries),
        "artifacts":entries,"encryption":encryption,"verification":"pending",
        "rpo_seconds":policy.rpo_seconds,"rto_seconds":policy.rto_seconds,"complete":True,
    }
    validate_manifest(manifest,verify_files=False)
    return manifest

def write_manifest(root,manifest):
    root=Path(root).resolve(); payload=dict(manifest); payload["verification"]="valid"
    envelope={"manifest":payload,"manifest_sha256":sha256(canonical_json(payload)).hexdigest()}
    target=root/"manifest.json"
    target.write_bytes(canonical_json(envelope)); target.chmod(0o600)
    return target

def validate_manifest(manifest,root=None,verify_files=True):
    if not isinstance(manifest,dict) or set(manifest)!=REQUIRED or manifest.get("schema_version")!=MANIFEST_VERSION:
        raise ManifestError("Manifesto incompleto ou versão desconhecida.")
    try: UUID(str(manifest["set_id"])); datetime.fromisoformat(manifest["created_at"])
    except (ValueError,TypeError) as exc: raise ManifestError("Identificador ou timestamp inválido.") from exc
    if manifest["complete"] is not True or manifest["verification"] not in {"pending","valid"}:
        raise ManifestError("Conjunto parcial ou não verificável.")
    if not isinstance(manifest["artifacts"],list) or manifest["item_count"]!=len(manifest["artifacts"]):
        raise ManifestError("Contagem de artefatos divergente.")
    if FORBIDDEN.search(canonical_json(manifest).decode("utf-8")):
        raise ManifestError("Manifesto contém campo proibido.")
    total=0
    for entry in manifest["artifacts"]:
        if set(entry)!=ARTIFACT_KEYS or not re.fullmatch(r"[0-9a-f]{64}",str(entry["sha256"])):
            raise ManifestError("Artefato inválido no manifesto.")
        UUID(str(entry["artifact_id"])); relative=Path(entry["relative_path"])
        if relative.is_absolute() or ".." in relative.parts: raise ManifestError("Caminho de artefato inválido.")
        total+=int(entry["size"])
        if verify_files:
            path=Path(root).resolve()/relative
            if not path.is_file() or path.stat().st_size!=entry["size"] or file_sha256(path)!=entry["sha256"]:
                raise ManifestError("Conjunto parcial ou adulterado.")
    if total!=manifest["total_bytes"]: raise ManifestError("Total de bytes divergente.")
    return manifest

def load_and_verify_manifest(root):
    root=Path(root).resolve()
    try: envelope=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ManifestError("Manifesto ausente ou truncado.") from exc
    if set(envelope)!={"manifest","manifest_sha256"} or sha256(canonical_json(envelope["manifest"])).hexdigest()!=envelope["manifest_sha256"]:
        raise ManifestError("Manifesto adulterado.")
    return validate_manifest(envelope["manifest"],root,True)
