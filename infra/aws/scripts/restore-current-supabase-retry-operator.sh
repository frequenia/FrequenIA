#!/usr/bin/env bash
set -euo pipefail

# Operator-only retry. Nothing decrypted is written to the host or printed.
# The initial partially restored database remains untouched for diagnosis.
backup_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
backup_file="$backup_dir/supabase-pilot-20261024-164527.dump.gpg"
expected_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
container='frequenia-restore-20261024'
database='frequenia_restore_retry_1'
image='pgvector/pgvector:pg17'

if [[ "$PWD" != "$backup_dir" || ! -r "$backup_file" ]] ||
   [[ "$(sha256sum "$backup_file" | awk '{print $1}')" != "$expected_sha" ]]; then
  printf 'Backup ausente ou hash divergente; nenhuma alteracao feita.\n' >&2
  exit 1
fi
if ! docker container inspect "$container" >/dev/null 2>&1; then
  printf 'Container isolado nao encontrado; nenhuma alteracao feita.\n' >&2
  exit 1
fi
if [[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" != none ]] ||
   [[ "$(docker inspect "$container" --format '{{json .NetworkSettings.Ports}}')" != '{}' ]]; then
  printf 'Isolamento do container nao confirmado; nenhuma alteracao feita.\n' >&2
  exit 1
fi
free_kib="$(df -Pk "$backup_dir" | awk 'NR == 2 { print $4 }')"
if [[ ! "$free_kib" =~ ^[0-9]+$ || "$free_kib" -lt 614400 ]]; then
  printf 'Espaco livre insuficiente (minimo: 600 MiB); nenhuma alteracao feita.\n' >&2
  exit 1
fi

umask 077
read -r -s -p 'Frase secreta do backup (nao aparece na tela): ' BACKUP_PASSPHRASE
printf '\n'
if [[ -z "$BACKUP_PASSPHRASE" ]]; then
  printf 'Frase secreta vazia; nenhuma alteracao feita.\n' >&2
  exit 1
fi
trap 'unset BACKUP_PASSPHRASE' EXIT

# Verify decryption and custom-archive framing without displaying the TOC.
if ! gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker run --rm --pull=never --network none -i --entrypoint pg_restore \
      "$image" --list >/dev/null 2>&1; then
  printf 'A frase secreta ou o arquivo nao passou na validacao; nenhum novo restore iniciado.\n' >&2
  exit 1
fi
printf 'Criptografia e formato do arquivo validados.\n'

if [[ "$(docker inspect "$container" --format '{{.State.Status}}')" != running ]]; then
  if ! docker start "$container" >/dev/null 2>&1; then
    printf 'Nao foi possivel iniciar o container isolado; backup preservado.\n' >&2
    exit 1
  fi
fi
ready=0
for ((attempt=0; attempt<30; attempt++)); do
  if docker exec "$container" pg_isready -q -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  printf 'PostgreSQL isolado nao ficou pronto; backup preservado.\n' >&2
  exit 1
fi
if docker exec "$container" psql -U postgres -d postgres -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = '$database'" 2>/dev/null | grep -qx 1; then
  printf 'Banco de retry ja existe; nada foi sobrescrito.\n' >&2
  exit 1
fi
if ! docker exec "$container" createdb -U postgres "$database" >/dev/null 2>&1; then
  printf 'Nao foi possivel criar banco isolado vazio; backup preservado.\n' >&2
  exit 1
fi

if ! restore_error="$(gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl \
      --dbname="$database" -U postgres 2>&1 >/dev/null)"; then
  case "$restore_error" in
    *'extension'*'is not available'*|*'could not open extension control file'*)
      printf 'Restore falhou: extensao do Supabase ausente na imagem local.\n' >&2 ;;
    *'role'*'does not exist'*)
      printf 'Restore falhou: papel interno do Supabase ausente na imagem local.\n' >&2 ;;
    *'already exists'*)
      printf 'Restore falhou: conflito de objeto no PostgreSQL local.\n' >&2 ;;
    *'permission denied'*)
      printf 'Restore falhou: permissao insuficiente no PostgreSQL local.\n' >&2 ;;
    *'connection'*|*'server closed'*)
      printf 'Restore falhou: conexao com o PostgreSQL isolado caiu.\n' >&2 ;;
    *) printf 'Restore falhou: erro nao classificado.\n' >&2 ;;
  esac
  unset restore_error
  printf 'Backup, container e bancos isolados preservados; nenhuma linha exibida.\n' >&2
  exit 1
fi
unset restore_error

if ! docker exec "$container" psql -U postgres -d "$database" \
    --no-psqlrc --quiet --tuples-only --no-align \
    --command "SELECT count(*) FROM pg_class WHERE relkind IN ('r','p')" \
    >/dev/null 2>&1; then
  printf 'Restore terminou, mas checagem de catalogo falhou; banco preservado.\n' >&2
  exit 1
fi
printf 'Restore completo validado no banco isolado; checagem de catalogo passou.\n'
printf 'Backup, container e bancos isolados preservados.\n'
