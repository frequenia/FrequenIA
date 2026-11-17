#!/usr/bin/env bash
set -euo pipefail

# Run only by the database operator from the ACL-restricted backup directory.
# Never print the connection URL, password, SQL output, or Docker diagnostics.
backup_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
if [[ "$PWD" != "$backup_dir" ]]; then
  printf 'Execute este script a partir da pasta privada de backup.\n' >&2
  exit 1
fi

ref_file="$backup_dir/supabase/.temp/project-ref"
url_file="$backup_dir/supabase/.temp/pooler-url"
ca_file="$backup_dir/supabase-prod-ca-2021.crt"
if [[ ! -r "$ref_file" || ! -r "$url_file" ]]; then
  printf 'Vinculo local do Supabase incompleto.\n' >&2
  exit 1
fi
if [[ ! -r "$ca_file" ]] || \
   [[ "$(sha256sum "$ca_file" | awk '{print $1}')" != 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]]; then
  printf 'CA publica do Supabase ausente ou alterada.\n' >&2
  exit 1
fi

linked_ref="$(tr -d '\r\n' < "$ref_file")"
if [[ ${#linked_ref} -ne 20 || "$linked_ref" != xoof*esgx ]]; then
  printf 'Projeto vinculado diferente do piloto; backup nao iniciado.\n' >&2
  exit 1
fi

if ! docker image inspect postgres:17-alpine >/dev/null 2>&1; then
  printf 'A imagem local postgres:17-alpine nao esta disponivel.\n' >&2
  exit 1
fi
if ! command -v gpg >/dev/null 2>&1; then
  printf 'GPG nao esta disponivel para criptografar o backup.\n' >&2
  exit 1
fi

free_kib="$(df -Pk "$backup_dir" | awk 'NR == 2 { print $4 }')"
if [[ ! "$free_kib" =~ ^[0-9]+$ || "$free_kib" -lt 524288 ]]; then
  printf 'Espaco livre insuficiente (minimo: 512 MiB); backup nao iniciado.\n' >&2
  exit 1
fi

timestamp="$(TZ=America/Sao_Paulo date +%Y%m%d-%H%M%S)"
output="$backup_dir/supabase-pilot-${timestamp}.dump.gpg"
partial="${output}.partial"
if [[ -e "$output" || -e "$partial" ]]; then
  printf 'Arquivo de destino ja existe; backup nao iniciado.\n' >&2
  exit 1
fi

umask 077
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]]; then
  printf 'Formato do vinculo invalido; backup nao iniciado.\n' >&2
  exit 1
fi
if [[ "$PGDATABASE" != *"$linked_ref"* ]]; then
  printf 'URL local e projeto vinculado divergem; backup nao iniciado.\n' >&2
  exit 1
fi
unset linked_ref
if [[ "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo contem TLS explicito; nao posso garantir verify-full.\n' >&2
  exit 1
fi
if [[ "${1:-}" == '--diagnose-dns' ]]; then
  authority="${PGDATABASE#*://}"
  authority="${authority%%/*}"
  endpoint="${authority##*@}"
  endpoint="${endpoint%%:*}"
  case "$endpoint" in
    *.pooler.supabase.com) printf 'Tipo do endpoint: pooler Supabase.\n' ;;
    db.*.supabase.co) printf 'Tipo do endpoint: direto Supabase.\n' ;;
    *) printf 'Tipo do endpoint: inesperado.\n' ;;
  esac
  if getent ahosts "$endpoint" >/dev/null 2>&1; then
    printf 'DNS do endpoint no WSL: ok.\n'
  else
    printf 'DNS do endpoint no WSL: falhou.\n'
  fi
  export PGHOST="$endpoint"
  if docker run --rm --pull=never --env PGHOST --entrypoint sh \
      postgres:17-alpine -c 'getent hosts "$PGHOST" >/dev/null 2>&1' \
      >/dev/null 2>&1; then
    printf 'DNS do endpoint no Docker: ok.\n'
  else
    printf 'DNS do endpoint no Docker: falhou.\n'
  fi
  unset PGDATABASE PGHOST authority endpoint
  exit 0
fi
read -r -s -p 'Senha do banco (nao aparece na tela): ' PGPASSWORD
printf '\n'
if [[ -z "$PGPASSWORD" ]]; then
  printf 'Senha vazia; conexao nao iniciada.\n' >&2
  exit 1
fi
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/supabase-ca.crt
export PGCONNECT_TIMEOUT=8
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT BACKUP_PASSPHRASE' EXIT

# Verify TLS and authentication with a constant query; never print the server's
# diagnostic because it can contain a complete connection string or hostname.
connection_ready=0
for attempt in 1 2 3; do
if connection_check="$(docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PGCONNECT_TIMEOUT \
    postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --command "SELECT 1"' 2>&1)"; then
  connection_ready=1
  break
fi
case "$connection_check" in
  *'could not translate host name'*|*'Name or service not known'*|*'connection timed out'*|*'Network is unreachable'*|*'No route to host'*)
    if [[ $attempt -lt 3 ]]; then
      printf 'Conexao temporariamente indisponivel; repetindo verificacao segura.\n'
      sleep 2
      continue
    fi ;;
esac
break
done
if [[ "$connection_ready" -ne 1 ]]; then
  case "$connection_check" in
    *'certificate'*|*'root certificate'*|*'SSL error'*)
      printf 'Diagnostico: falha de verificacao TLS. Nenhum dump iniciado.\n' >&2 ;;
    *'password authentication failed'*|*'no password supplied'*|*'SASL'*|*'SCRAM'*)
      printf 'Diagnostico: autenticacao do banco recusada. Nenhum dump iniciado.\n' >&2 ;;
    *'could not translate host name'*|*'Name or service not known'*)
      printf 'Diagnostico: DNS do banco indisponivel. Nenhum dump iniciado.\n' >&2 ;;
    *'Connection refused'*|*'connection timed out'*|*'Network is unreachable'*|*'No route to host'*)
      printf 'Diagnostico: conexao de rede indisponivel. Nenhum dump iniciado.\n' >&2 ;;
    *) printf 'Diagnostico: falha de conexao nao classificada. Nenhum dump iniciado.\n' >&2 ;;
  esac
  exit 1
fi
unset connection_check

read -r -s -p 'Frase secreta NOVA para o backup (guarde fora deste computador): ' BACKUP_PASSPHRASE
printf '\n'
read -r -s -p 'Repita a frase secreta do backup: ' BACKUP_PASSPHRASE_AGAIN
printf '\n'
if [[ ${#BACKUP_PASSPHRASE} -lt 16 || "$BACKUP_PASSPHRASE" != "$BACKUP_PASSPHRASE_AGAIN" ]]; then
  printf 'Frase secreta curta ou diferente; backup nao iniciado.\n' >&2
  exit 1
fi
unset BACKUP_PASSPHRASE_AGAIN

if ! docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PGCONNECT_TIMEOUT \
    postgres:17-alpine -c 'exec pg_dump --dbname="$PGDATABASE" --format=custom --no-owner --no-acl' \
    2>/dev/null | gpg --batch --yes --pinentry-mode loopback \
      --no-symkey-cache --symmetric --cipher-algo AES256 --compress-algo none \
      --passphrase-fd 3 --output "$partial" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null; then
  printf 'Dump falhou. Arquivo parcial criptografado preservado; nao o compartilhe.\n' >&2
  exit 1
fi
if [[ ! -s "$partial" ]]; then
  printf 'Dump vazio; arquivo parcial privado preservado.\n' >&2
  exit 1
fi

mv -- "$partial" "$output"
printf 'Dump criptografado criado com TLS verify-full solicitado.\n'
stat -c 'Bytes: %s' "$output"
sha256sum "$output"
