#!/usr/bin/env bash
set -euo pipefail
umask 077

# Ensaio local, sem rede e sem portas publicadas. Nunca conecta ao Supabase.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
repo_dir='/mnt/c/Users/lavin/Downloads/FrequenIA'
backup_file="$private_dir/supabase-pilot-20261024-164527.dump.gpg"
expected_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
container='frequenia-restore-20261024'
database='frequenia_recovery_rehearsal_20261114_3'
log_file="$private_dir/recovery-rehearsal-$(TZ=America/Sao_Paulo date +%Y%m%d-%H%M%S).private.log"

if [[ "$PWD" != "$private_dir" || ! -r "$backup_file" ]] ||
   [[ "$(sha256sum "$backup_file" | awk '{print $1}')" != "$expected_sha" ]]; then
  printf 'Backup protegido ausente ou alterado; ensaio nao iniciado.\n' >&2
  exit 1
fi
if [[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" != none ]] ||
   [[ "$(docker inspect "$container" --format '{{json .NetworkSettings.Ports}}')" != '{}' ]]; then
  printf 'Container isolado nao confirmado; ensaio nao iniciado.\n' >&2
  exit 1
fi
mapfile -t migrations < <(find "$repo_dir/supabase/migrations" -maxdepth 1 -type f \
  -name '[0-9][0-9][0-9]_*.sql' -printf '%f\n' | sort)
if [[ ${#migrations[@]} -ne 26 || "${migrations[0]}" != 001_* || "${migrations[25]}" != 026_* ]]; then
  printf 'Sequencia local de migrations inesperada; ensaio nao iniciado.\n' >&2
  exit 1
fi

read -r -s -p 'Frase secreta do backup de 24/10 (nao aparece na tela): ' BACKUP_PASSPHRASE
printf '\n'
if [[ -z "$BACKUP_PASSPHRASE" ]]; then
  printf 'Frase secreta vazia; ensaio nao iniciado.\n' >&2
  exit 1
fi
trap 'unset BACKUP_PASSPHRASE; docker stop -t 20 "$container" >/dev/null 2>&1 || true' EXIT

if ! gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker run --rm --pull=never --network none -i --entrypoint pg_restore \
      pgvector/pgvector:pg17 --list >/dev/null 2>&1; then
  printf 'Frase secreta ou arquivo invalido; ensaio nao iniciado.\n' >&2
  exit 1
fi

docker start "$container" >/dev/null
ready=0
for _attempt in $(seq 1 30); do
  if docker exec "$container" pg_isready -q -U postgres; then
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
    "SELECT 1 FROM pg_database WHERE datname='$database'" 2>/dev/null | grep -qx 1; then
  printf 'Banco de ensaio ja existe; nada foi sobrescrito.\n' >&2
  exit 1
fi
docker exec "$container" createdb -U postgres "$database" >/dev/null

for migration in "${migrations[@]}"; do
  if ! docker exec -i "$container" psql -U postgres -d "$database" \
      --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --file=- \
      < "$repo_dir/supabase/migrations/$migration" >>"$log_file" 2>&1; then
    chmod 600 "$log_file"
    printf 'Schema atual falhou no PostgreSQL isolado; banco e log privado preservados.\n' >&2
    exit 1
  fi
done

read -r -d '' RESTORE_PREFIX <<'SQL' || true
\set ON_ERROR_STOP on
BEGIN;
DO $block$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT conrelid, conname
    FROM pg_constraint
    WHERE contype = 'f' AND connamespace = 'public'::regnamespace
  LOOP
    EXECUTE format(
      'ALTER TABLE %s ALTER CONSTRAINT %I DEFERRABLE INITIALLY DEFERRED',
      item.conrelid::regclass,
      item.conname
    );
  END LOOP;
END
$block$;
SQL
read -r -d '' RESTORE_SUFFIX <<'SQL' || true
SET CONSTRAINTS ALL IMMEDIATE;
DO $block$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT conrelid, conname
    FROM pg_constraint
    WHERE contype = 'f' AND connamespace = 'public'::regnamespace
  LOOP
    EXECUTE format(
      'ALTER TABLE %s ALTER CONSTRAINT %I NOT DEFERRABLE',
      item.conrelid::regclass,
      item.conname
    );
  END LOOP;
END
$block$;
COMMIT;
SQL

set +e
{
  printf '%s\n' "$RESTORE_PREFIX"
  if ! gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
      --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker exec -i "$container" pg_restore -U postgres \
      --exit-on-error --no-owner --no-acl --data-only --schema=public --file=-; then
    exit 41
  fi
  printf '%s\n' "$RESTORE_SUFFIX"
} 2>>"$log_file" |
  docker exec -i "$container" psql -U postgres -d "$database" \
    --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --file=- >>"$log_file" 2>&1
pipeline_status=("${PIPESTATUS[@]}")
set -e
chmod 600 "$log_file"
if [[ "${pipeline_status[0]}" -ne 0 || "${pipeline_status[1]}" -ne 0 ]]; then
  printf 'Restore de dados falhou no ensaio; banco e log privado preservados.\n' >&2
  exit 1
fi

read -r -d '' CENSUS_SQL <<'SQL' || true
SELECT
  (SELECT count(*) FROM public.usuarios),
  (SELECT count(*) FROM public.empresas),
  (SELECT count(*) FROM public.funcionarios),
  (SELECT count(*) FROM public.biometrias),
  (SELECT count(*) FROM public.marcacoes),
  (SELECT count(*) FROM public.terminais_ponto),
  (SELECT count(*) FROM public.jornadas_diarias),
  (SELECT count(*) FROM public.tentativas_faciais);
SQL
if ! result="$(printf '%s\n' "$CENSUS_SQL" | docker exec -i "$container" \
    psql -U postgres -d "$database" --no-psqlrc --quiet --tuples-only \
    --no-align --set=ON_ERROR_STOP=1 --file=- 2>>"$log_file")"; then
  printf 'Validacao do ensaio falhou; nenhuma linha foi exibida.\n' >&2
  exit 1
fi
if [[ ! "$result" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]]; then
  printf 'Validacao do ensaio retornou formato inesperado.\n' >&2
  exit 1
fi
IFS='|' read -r users companies employees biometrics markings terminals journeys attempts <<< "$result"
printf 'ensaio_censo: usuarios=%s; empresas=%s; funcionarios=%s; biometrias=%s; marcacoes=%s; terminais=%s; jornadas=%s; tentativas_faciais=%s.\n' \
  "$users" "$companies" "$employees" "$biometrics" "$markings" "$terminals" "$journeys" "$attempts"
printf 'Ensaio local concluido; Supabase ativo nao foi alterado.\n'
