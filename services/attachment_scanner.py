"""Scanner antimalware fail-closed por protocolo ClamAV INSTREAM."""
import os
import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

class ScannerError(Exception): pass

class ScanResult:
    def __init__(self, status, code): self.status, self.code = status, code

@dataclass(frozen=True)
class SignatureInfo:
    engine_version: str
    database_version: str
    updated_at: datetime

    @property
    def age_hours(self):
        return max(0.0,(datetime.now(timezone.utc)-self.updated_at).total_seconds()/3600)

class ClamAVScanner:
    def __init__(self, host, port=3310, timeout=10, max_bytes=10*1024*1024):
        self.host=str(host or "").strip(); self.port=int(port); self.timeout=float(timeout); self.max_bytes=int(max_bytes)
        if not self.host: raise ScannerError("Scanner antimalware não configurado.")
    def scan(self, content):
        if not content or len(content)>self.max_bytes: raise ScannerError("Conteúdo fora do limite de varredura.")
        try:
            with socket.create_connection((self.host,self.port),timeout=self.timeout) as connection:
                connection.settimeout(self.timeout); connection.sendall(b"zINSTREAM\0")
                for offset in range(0,len(content),65536):
                    chunk=content[offset:offset+65536]; connection.sendall(struct.pack("!I",len(chunk))+chunk)
                connection.sendall(struct.pack("!I",0)); response=connection.recv(4096).decode("utf-8","replace")
        except (OSError, socket.timeout) as exc: raise ScannerError("Scanner antimalware indisponível.") from exc
        if response.endswith("OK\0"): return ScanResult("limpo","clean")
        if "FOUND" in response: return ScanResult("infectado","malware_detected")
        raise ScannerError("Resposta inválida do scanner antimalware.")
    def healthcheck(self):
        try:
            with socket.create_connection((self.host,self.port),timeout=self.timeout) as connection:
                connection.sendall(b"zPING\0"); return connection.recv(64).startswith(b"PONG")
        except OSError: return False
    def signature_info(self):
        try:
            with socket.create_connection((self.host,self.port),timeout=self.timeout) as connection:
                connection.settimeout(self.timeout); connection.sendall(b"zVERSION\0")
                response=connection.recv(512).decode("utf-8","replace").strip("\0\r\n ")
        except (OSError,socket.timeout) as exc:
            raise ScannerError("Versão das assinaturas indisponível.") from exc
        parts=response.split("/",2)
        if len(parts)!=3 or not parts[0].startswith("ClamAV ") or not parts[1].isdigit():
            raise ScannerError("Resposta inválida da versão das assinaturas.")
        try:
            updated=parsedate_to_datetime(parts[2])
            if updated.tzinfo is None: updated=updated.replace(tzinfo=timezone.utc)
            updated=updated.astimezone(timezone.utc)
        except (TypeError,ValueError,OverflowError) as exc:
            raise ScannerError("Data das assinaturas inválida.") from exc
        return SignatureInfo(parts[0].removeprefix("ClamAV "),parts[1],updated)
    def signatures_current(self):
        try: maximum=min(max(float(os.getenv("CLAMAV_SIGNATURE_MAX_AGE_HOURS","48")),1),720)
        except ValueError: return False
        try: return self.signature_info().age_hours <= maximum
        except ScannerError: return False

class FakeScanner:
    def __init__(self, result="limpo"): self.result=result
    def scan(self, content):
        if self.result=="erro": raise ScannerError("Falha controlada.")
        return ScanResult(self.result,"clean" if self.result=="limpo" else "malware_detected")
    def healthcheck(self): return self.result!="erro"
    def signature_info(self): return SignatureInfo("test","1",datetime.now(timezone.utc))
    def signatures_current(self): return self.result!="erro"

def get_attachment_scanner():
    provider=os.getenv("ATTACHMENT_SCANNER_PROVIDER","clamav").strip().lower()
    environment=os.getenv("APP_ENV","development").strip().lower()
    if provider.startswith("fake-"):
        if environment not in {"test","testing"}: raise ScannerError("Scanner falso só é permitido em testes.")
        result={"clean":"limpo","infected":"infectado","error":"erro"}.get(provider.removeprefix("fake-"))
        if not result: raise ScannerError("Resultado de scanner falso inválido.")
        return FakeScanner(result)
    if provider!="clamav": raise ScannerError("Provedor de scanner inválido.")
    return ClamAVScanner(os.getenv("CLAMAV_HOST"),os.getenv("CLAMAV_PORT","3310"),os.getenv("CLAMAV_TIMEOUT_SECONDS","10"))
