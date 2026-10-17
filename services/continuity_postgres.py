"""Exportação/restauração PostgreSQL somente para exercícios descartáveis.

Credenciais são passadas ao subprocesso pelo ambiente e nunca compõem argv/logs.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
from urllib.parse import unquote,urlparse


class PostgresContinuityError(RuntimeError): pass


def _local_container_client(tool, database, args, *, input_bytes=None):
    """Cliente PostgreSQL opcional, restrito a exercício local descartável.

    A senha não entra em argv: o shell dentro do contêiner usa a variável
    POSTGRES_PASSWORD já definida no próprio recurso descartável.
    """
    container=os.environ.get("FREQUENIA_PG_CLIENT_CONTAINER","").strip()
    if not container:return None
    if os.environ.get("APP_ENV","development").strip().lower()=="production":
        raise PostgresContinuityError("Cliente PostgreSQL em contêiner é proibido em produção.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}",container):
        raise PostgresContinuityError("Contêiner PostgreSQL descartável inválido.")
    prefix=["docker"]
    if os.name=="nt":prefix=["wsl","-d","Ubuntu","-u","root","--","docker"]
    safe_command=shlex.join([tool,*args])
    command=[*prefix,"exec","-i",container,"sh","-c",
             f'export PGPASSWORD="$POSTGRES_PASSWORD"; exec {safe_command}']
    try:
        return subprocess.run(command,input=input_bytes,capture_output=True,check=False,timeout=300)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise PostgresContinuityError("Ferramenta PostgreSQL descartável indisponível ou expirou.") from exc


@dataclass(frozen=True)
class DisposableDatabase:
    host:str
    port:int
    database:str
    user:str
    password:str


def parse_disposable_database(url):
    parsed=urlparse(str(url or ""))
    database=unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres","postgresql"} or not parsed.hostname or not parsed.username:
        raise PostgresContinuityError("URL PostgreSQL descartável inválida.")
    if not re.fullmatch(r"frequenia_[a-z0-9_]*test",database):
        raise PostgresContinuityError("Banco deve possuir nome descartável explícito.")
    if parsed.hostname not in {"localhost","127.0.0.1","::1","frequenia-phase29-postgres"}:
        raise PostgresContinuityError("Host PostgreSQL não é descartável/autorizado.")
    return DisposableDatabase(parsed.hostname,parsed.port or 5432,database,unquote(parsed.username),unquote(parsed.password or ""))


def _run(args,database,runner=subprocess.run):
    safe_env=os.environ.copy(); safe_env["PGPASSWORD"]=database.password
    resolved_args=list(args)
    if runner is subprocess.run:
        executable=shutil.which(args[0],path=safe_env.get("PATH"))
        if not executable:
            raise PostgresContinuityError("Ferramenta PostgreSQL indisponível ou expirou.")
        resolved_args=[executable,*args[1:]]
        if os.name == "nt" and Path(executable).suffix.lower() in {".cmd",".bat"}:
            resolved_args=[safe_env.get("COMSPEC","cmd.exe"),"/d","/c",*resolved_args]
    try:
        completed=runner(resolved_args,env=safe_env,capture_output=True,text=True,check=False,timeout=300)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise PostgresContinuityError("Ferramenta PostgreSQL indisponível ou expirou.") from exc
    if completed.returncode:
        raise PostgresContinuityError("Operação PostgreSQL falhou; saída foi omitida para proteger credenciais.")


def export_custom(database_url,target,runner=subprocess.run):
    database=parse_disposable_database(database_url); target=Path(target).resolve()
    target.parent.mkdir(parents=True,exist_ok=True); target.parent.chmod(0o700)
    container_args=["--format=custom","--no-owner","--no-acl","--host","127.0.0.1",
                    "--port","5432","--username",database.user,database.database]
    completed=_local_container_client("pg_dump",database,container_args)
    if completed is not None:
        if completed.returncode or not completed.stdout:
            raise PostgresContinuityError("Operação PostgreSQL falhou; saída foi omitida para proteger credenciais.")
        target.write_bytes(completed.stdout)
        target.chmod(0o600)
        return target
    args=["pg_dump","--format=custom","--no-owner","--no-acl","--host",database.host,"--port",str(database.port),"--username",database.user,"--file",str(target),database.database]
    _run(args,database,runner)
    if not target.is_file() or target.stat().st_size==0: raise PostgresContinuityError("Dump ausente ou vazio.")
    target.chmod(0o600); return target


def restore_custom(database_url,dump_path,runner=subprocess.run):
    database=parse_disposable_database(database_url); dump_path=Path(dump_path).resolve()
    if not dump_path.is_file() or dump_path.stat().st_size==0: raise PostgresContinuityError("Dump ausente ou vazio.")
    container_args=["--exit-on-error","--clean","--if-exists","--no-owner","--no-acl",
                    "--host","127.0.0.1","--port","5432","--username",database.user,
                    "--dbname",database.database]
    completed=_local_container_client("pg_restore",database,container_args,input_bytes=dump_path.read_bytes())
    if completed is not None:
        if completed.returncode:
            raise PostgresContinuityError("Operação PostgreSQL falhou; saída foi omitida para proteger credenciais.")
        return True
    args=["pg_restore","--exit-on-error","--clean","--if-exists","--no-owner","--no-acl","--host",database.host,"--port",str(database.port),"--username",database.user,"--dbname",database.database,str(dump_path)]
    _run(args,database,runner); return True
