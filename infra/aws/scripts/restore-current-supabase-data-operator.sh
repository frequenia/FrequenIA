#!/usr/bin/env bash
set -euo pipefail
umask 077

# Recuperacao de dados no projeto ativo. Exige backup forense previo, alvo vazio
# e confirmacao humana. O restore usa uma unica transacao e nao altera schema.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
old_backup="$private_dir/supabase-pilot-20261024-164527.dump.gpg"
old_backup_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
ref_file="$private_dir/supabase/.temp/project-ref"
url_file="$private_dir/supabase/.temp/pooler-url"
ca_file="$private_dir/supabase-prod-ca-2021.crt"
log_file="$private_dir/active-recovery-$(TZ=America/Sao_Paulo date +%Y%m%d-%H%M%S).private.log"

if [[ "$PWD" != "$private_dir" || ! -r "$old_backup" ]] ||
   [[ "$(sha256sum "$old_backup" | awk '{print $1}')" != "$old_backup_sha" ]]; then
  printf 'Backup de recuperacao ausente ou alterado; restore nao iniciado.\n' >&2
  exit 1
fi
for file in "$ref_file" "$url_file" "$ca_file"; do
  if [[ ! -r "$file" ]]; then
    printf 'Vinculo privado incompleto; restore nao iniciado.\n' >&2
    exit 1
  fi
done
if [[ "$(sha256sum "$ca_file" | awk '{print $1}')" != 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]]; then
  printf 'CA publica ausente ou alterada; restore nao iniciado.\n' >&2
  exit 1
fi

forensic_file="$(find "$private_dir" -maxdepth 1 -type f \
  -name 'supabase-pilot-*.dump.gpg' ! -name 'supabase-pilot-20261024-164527.dump.gpg' \
  -printf '%T@|%p\n' | sort -n | tail -n 1 | cut -d'|' -f2-)"
if [[ -z "$forensic_file" || ! -s "$forensic_file" ]]; then
  printf 'Backup forense do estado atual ausente; restore nao iniciado.\n' >&2
  exit 1
fi
forensic_sha="$(sha256sum "$forensic_file" | awk '{print $1}')"
if [[ ! "$forensic_sha" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'Hash do backup forense invalido; restore nao iniciado.\n' >&2
  exit 1
fi

linked_ref="$(tr -d '\r\n' < "$ref_file")"
if [[ ${#linked_ref} -ne 20 || "$linked_ref" != xoof*esgx ]]; then
  printf 'Projeto vinculado diferente do piloto; restore nao iniciado.\n' >&2
  exit 1
fi
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]] ||
   [[ "$PGDATABASE" != *"$linked_ref"* ]] ||
   [[ "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo privado invalido; restore nao iniciado.\n' >&2
  exit 1
fi
unset linked_ref
if ! docker image inspect postgres:17-alpine >/dev/null 2>&1; then
  printf 'Imagem PostgreSQL local indisponivel; restore nao iniciado.\n' >&2
  exit 1
fi

read -r -s -p 'Senha do banco ativo (nao aparece na tela): ' PGPASSWORD
printf '\n'
read -r -s -p 'Frase secreta do backup de 24/10 (nao aparece na tela): ' BACKUP_PASSPHRASE
printf '\n'
read -r -p 'Digite RESTAURAR-DADOS-24-10 para confirmar: ' CONFIRMATION
if [[ -z "$PGPASSWORD" || -z "$BACKUP_PASSPHRASE" ||
      "$CONFIRMATION" != 'RESTAURAR-DADOS-24-10' ]]; then
  printf 'Confirmacao ou segredo ausente; restore nao iniciado.\n' >&2
  exit 1
fi
unset CONFIRMATION
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/supabase-ca.crt
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT BACKUP_PASSPHRASE' EXIT

if ! gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$old_backup" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker run --rm --pull=never --network none -i --entrypoint pg_restore \
      postgres:17-alpine --list >/dev/null 2>&1; then
  printf 'Backup ou frase secreta invalida; restore nao iniciado.\n' >&2
  exit 1
fi

read -r -d '' PREFLIGHT_SQL <<'SQL' || true
SELECT
  (to_regclass('public.usuarios') IS NOT NULL)::int,
  (to_regclass('public.politicas_biometricas') IS NOT NULL)::int,
  (SELECT count(*) FROM public.usuarios),
  (SELECT count(*) FROM public.empresas),
  (SELECT count(*) FROM public.funcionarios),
  (SELECT count(*) FROM public.biometrias),
  (SELECT count(*) FROM public.marcacoes),
  (SELECT count(*) FROM public.terminais_ponto),
  (SELECT count(*) FROM public.jornadas_diarias),
  (SELECT count(*) FROM public.tentativas_faciais);
SQL
export PREFLIGHT_SQL
if ! preflight="$(docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
    --env PREFLIGHT_SQL postgres:17-alpine -c \
      'printf "%s\n" "$PREFLIGHT_SQL" | exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-' \
    2>>"$log_file")"; then
  chmod 600 "$log_file"
  printf 'Preflight remoto falhou; restore nao iniciado.\n' >&2
  exit 1
fi
if [[ "$preflight" != '1|1|0|0|0|0|0|0|0|0' ]]; then
  chmod 600 "$log_file"
  printf 'Banco ativo nao esta no estado vazio esperado; restore nao iniciado.\n' >&2
  exit 1
fi

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
      --passphrase-fd 3 --decrypt "$old_backup" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker run --rm --pull=never --network none -i --entrypoint pg_restore \
      postgres:17-alpine --exit-on-error --no-owner --no-acl \
        --data-only --schema=public --file=-; then
    exit 41
  fi
  printf '%s\n' "$RESTORE_SUFFIX"
} 2>>"$log_file" |
  docker run --rm --pull=never -i --entrypoint psql \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
    postgres:17-alpine --dbname="$PGDATABASE" --no-psqlrc --quiet \
      --set=ON_ERROR_STOP=1 --file=- >>"$log_file" 2>&1
pipeline_status=("${PIPESTATUS[@]}")
set -e
chmod 600 "$log_file"
if [[ "${pipeline_status[0]}" -ne 0 || "${pipeline_status[1]}" -ne 0 ]]; then
  printf 'Restore falhou e a transacao foi abortada; log privado preservado.\n' >&2
  exit 1
fi

read -r -d '' VERIFY_SQL <<'SQL' || true
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
export VERIFY_SQL
if ! result="$(docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
    --env VERIFY_SQL postgres:17-alpine -c \
      'printf "%s\n" "$VERIFY_SQL" | exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-' \
    2>>"$log_file")"; then
  printf 'Restore concluiu, mas a verificacao agregada falhou; pare a publicacao.\n' >&2
  exit 1
fi
if [[ "$result" != '17|2|16|2|10|1|1|14' ]]; then
  printf 'Restore concluiu com contagens inesperadas; pare a publicacao.\n' >&2
  exit 1
fi
printf 'restore_censo: usuarios=17; empresas=2; funcionarios=16; biometrias=2; marcacoes=10; terminais=1; jornadas=1; tentativas_faciais=14.\n'
printf 'Restore de dados concluido em transacao unica. Politica/perfil continuam pendentes.\n'
printf 'forensic_sha256=%s\n' "$forensic_sha"
