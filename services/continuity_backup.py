"""Preparação e restauração explícitas de conjuntos sintéticos descartáveis."""
from pathlib import Path
import os
import shutil
import tempfile

from services.backup_manifest import build_manifest,load_and_verify_manifest,write_manifest
from services.continuity_policy import load_continuity_policy

class ContinuityBackupError(RuntimeError): pass

def _safe_environment(value):
    value=str(value or "").strip().lower()
    if value in {"production","prod"}: raise ContinuityBackupError("Produção é recusada por esta ferramenta.")
    if value not in {"development","test","testing","staging-isolated"}: raise ContinuityBackupError("Ambiente descartável inválido.")
    return value

def _outside_repository(path):
    path=Path(path).resolve(); repository=Path(__file__).resolve().parents[1]
    public=(repository/"static").resolve()
    if path==repository or repository in path.parents or path==public or public in path.parents:
        raise ContinuityBackupError("Conjunto deve ficar fora do repositório e de diretórios públicos.")
    return path

def prepare_backup_set(destination,artifacts,migrations,environment="test",execute=False,policy=None):
    destination=_outside_repository(destination); environment=_safe_environment(environment)
    policy=policy or load_continuity_policy(environment)
    if not artifacts: raise ContinuityBackupError("Conjunto sem artefatos não é restaurável.")
    total=sum(Path(item["source"]).stat().st_size for item in artifacts)
    plan={"dry_run":not execute,"artifact_count":len(artifacts),"total_bytes":total,"production_status":policy.production_status}
    if total>policy.max_set_bytes: raise ContinuityBackupError("Conjunto excede o limite configurado.")
    if not execute: return plan
    if destination.exists() and any(destination.iterdir()): raise ContinuityBackupError("Destino não vazio.")
    destination.mkdir(parents=True,exist_ok=True); destination.chmod(0o700)
    created=[]
    try:
        for index,item in enumerate(artifacts,1):
            source=Path(item["source"]).resolve()
            name=f"artifact-{index:04d}.bin"; target=destination/name
            shutil.copyfile(source,target); target.chmod(0o600)
            created.append({"path":target,"relative_path":name,"component":item["component"]})
        manifest=build_manifest(created,environment,migrations,policy)
        write_manifest(destination,manifest); load_and_verify_manifest(destination)
        return {**plan,"dry_run":False,"set_id":manifest["set_id"],"verified":True}
    except Exception:
        shutil.rmtree(destination,ignore_errors=True)
        raise

def restore_backup_set(source,destination,environment="test",execute=False,allow_nonempty=False,interrupt_after=None):
    source=_outside_repository(source); destination=_outside_repository(destination); _safe_environment(environment)
    if source==destination: raise ContinuityBackupError("Origem e destino devem ser diferentes.")
    manifest=load_and_verify_manifest(source)
    plan={"dry_run":not execute,"set_id":manifest["set_id"],"artifact_count":manifest["item_count"]}
    if not execute: return plan
    if destination.exists() and any(destination.iterdir()) and not allow_nonempty:
        raise ContinuityBackupError("Destino não vazio.")
    destination.mkdir(parents=True,exist_ok=True); destination.chmod(0o700)
    journal=destination/"restore.journal"
    completed=set(journal.read_text(encoding="utf-8").splitlines()) if journal.exists() else set()
    for index,entry in enumerate(manifest["artifacts"],1):
        if entry["artifact_id"] in completed: continue
        shutil.copyfile(source/entry["relative_path"],destination/entry["relative_path"])
        with journal.open("a",encoding="utf-8") as handle: handle.write(entry["artifact_id"]+"\n"); handle.flush(); os.fsync(handle.fileno())
        if interrupt_after and index>=interrupt_after: raise ContinuityBackupError("Restauração interrompida de forma controlada.")
    shutil.copyfile(source/"manifest.json",destination/"manifest.json")
    (destination/"manifest.json").chmod(0o600)
    restored=load_and_verify_manifest(destination)
    (destination/"restore.complete").write_text(restored["set_id"],encoding="ascii")
    return {**plan,"dry_run":False,"verified":True,"resumed":bool(completed)}

def isolated_temporary_directory(prefix="frequenia-continuity-"):
    return tempfile.TemporaryDirectory(prefix=prefix)
