#!/usr/bin/env bash
set -euo pipefail

# Validate the application schema/data only. This is not a full Supabase restore.
# The operator enters the passphrase privately; no rows or SQL errors are shown.
backup_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
backup_file="$backup_dir/supabase-pilot-20261024-164527.dump.gpg"
expected_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
container='frequenia-restore-20261024'
database='frequenia_restore_public_1'

if [[ "$PWD" != "$backup_dir" || ! -r "$backup_file" ]] ||
   [[ "$(sha256sum "$backup_file" | awk '{print $1}')" != "$expected_sha" ]]; then
  printf 'Backup ausente ou hash divergente; nenhuma alteracao feita.\n' >&2
  exit 1
fi
if ! docker container inspect "$container" >/dev/null 2>&1 ||
   [[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" != none ]] ||
   [[ "$(docker inspect "$container" --format '{{json .NetworkSettings.Ports}}')" != '{}' ]]; then
  printf 'Container isolado nao confirmado; nenhuma alteracao feita.\n' >&2
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

if [[ "$(docker inspect "$container" --format '{{.State.Status}}')" != running ]]; then
  if ! docker start "$container" >/dev/null 2>&1; then
    printf 'Nao foi possivel iniciar o PostgreSQL isolado.\n' >&2
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
  printf 'PostgreSQL isolado nao ficou pronto.\n' >&2
  exit 1
fi
if docker exec "$container" psql -U postgres -d postgres -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = '$database'" 2>/dev/null | grep -qx 1; then
  printf 'Banco de validacao ja existe; nada foi sobrescrito.\n' >&2
  exit 1
fi
if ! docker exec "$container" createdb -U postgres "$database" >/dev/null 2>&1; then
  printf 'Nao foi possivel criar banco de validacao vazio.\n' >&2
  exit 1
fi
if ! docker exec "$container" psql -U postgres -d "$database" -v ON_ERROR_STOP=1 \
    -c 'CREATE SCHEMA extensions; CREATE EXTENSION pgcrypto WITH SCHEMA extensions; CREATE EXTENSION vector WITH SCHEMA extensions;' \
    >/dev/null 2>&1; then
  printf 'Nao foi possivel preparar pgcrypto/vector; banco isolado preservado.\n' >&2
  exit 1
fi

if ! restore_error="$(gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl \
      --schema=public --dbname="$database" -U postgres 2>&1 >/dev/null)"; then
  case "$restore_error" in
    *'extension'*'is not available'*|*'could not open extension control file'*)
      printf 'Restore public falhou: outra extensao ausente.\n' >&2 ;;
    *'role'*'does not exist'*)
      printf 'Restore public falhou: papel interno ausente.\n' >&2 ;;
    *'schema'*'does not exist'*|*'type'*'does not exist'*|*'function'*'does not exist'*)
      printf 'Restore public falhou: dependencia fora do schema public.\n' >&2 ;;
    *'already exists'*)
      printf 'Restore public falhou: objeto ja existe no banco vazio.\n' >&2 ;;
    *'COPY'*|*'violates'*|*'constraint'*)
      printf 'Restore public falhou ao carregar ou validar dados.\n' >&2 ;;
    *) printf 'Restore public falhou: erro nao classificado.\n' >&2 ;;
  esac
  unset restore_error
  printf 'Backup e bancos isolados preservados; nenhuma linha exibida.\n' >&2
  exit 1
fi
unset restore_error

if ! docker exec "$container" psql -U postgres -d "$database" -Atqc \
    "SELECT count(*) > 0 FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','p')" \
    2>/dev/null | grep -qx t; then
  printf 'Restore public terminou, mas nao confirmou tabelas; banco preservado.\n' >&2
  exit 1
fi
printf 'Schema public e respectivos dados restaurados no PostgreSQL isolado.\n'
printf 'Validacao parcial: schemas internos Supabase nao foram restaurados.\n'
printf 'Backup e bancos isolados preservados; nenhuma linha exibida.\n'
