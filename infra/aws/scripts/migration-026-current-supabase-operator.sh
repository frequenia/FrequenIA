#!/usr/bin/env bash
set -euo pipefail
umask 077

# Operator-only workflow. Run from the ACL-restricted private backup directory.
# Never paste the password, URL, private log, or SQL output into chat.
backup_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
repo_dir='/mnt/c/Users/lavin/Downloads/FrequenIA'
backup_file="$backup_dir/supabase-pilot-20261024-164527.dump.gpg"
backup_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
ref_file="$backup_dir/supabase/.temp/project-ref"
url_file="$backup_dir/supabase/.temp/pooler-url"
ca_file="$backup_dir/supabase-prod-ca-2021.crt"
migration_file="$repo_dir/supabase/migrations/026_biometric_governance_lifecycle.sql"
migration_sha='39b46282182d269f5f2279d6fca5e1d36f75294c72229aaae6f700b412a7baa0'
log_file="$backup_dir/migration-026-$(TZ=America/Sao_Paulo date +%Y%m%d-%H%M%S).private.log"

if [[ "$PWD" != "$backup_dir" ]]; then
  printf 'Execute a partir da pasta privada de backup.\n' >&2
  exit 1
fi
if [[ "${1:-}" == '--classify-last-failure' ]]; then
  last_log="$(find "$backup_dir" -maxdepth 1 -type f -name 'migration-026-*.private.log' \
    -printf '%f\n' | sort | tail -n 1)"
  if [[ -z "$last_log" ]]; then
    printf 'Diagnostico: nenhum log privado encontrado.\n'
    exit 0
  fi
  last_log="$backup_dir/$last_log"
  if grep -Eqi 'password authentication failed|no password supplied|SASL|SCRAM' "$last_log"; then
    printf 'Diagnostico: autenticacao recusada.\n'
  elif grep -Eqi 'certificate|SSL error|root certificate|verify-full' "$last_log"; then
    printf 'Diagnostico: falha de verificacao TLS.\n'
  elif grep -Eqi 'could not translate host name|Name or service not known|temporary failure in name resolution' "$last_log"; then
    printf 'Diagnostico: DNS indisponivel.\n'
  elif grep -Eqi 'Connection refused|connection timed out|Network is unreachable|No route to host|server closed' "$last_log"; then
    printf 'Diagnostico: conexao de rede indisponivel.\n'
  elif grep -Eqi 'permission denied|must be owner|insufficient privilege' "$last_log"; then
    printf 'Diagnostico: permissao do banco insuficiente.\n'
  elif grep -Eqi 'Cannot connect to the Docker daemon|error during connect|docker:' "$last_log"; then
    printf 'Diagnostico: Docker indisponivel.\n'
  elif grep -Eqi 'ERROR:|syntax error|invalid input syntax' "$last_log"; then
    printf 'Diagnostico: consulta SQL recusada.\n'
  else
    printf 'Diagnostico: falha nao classificada; log privado preservado.\n'
  fi
  exit 0
fi
for file in "$backup_file" "$ref_file" "$url_file" "$ca_file" "$migration_file"; do
  if [[ ! -r "$file" ]]; then
    printf 'Preparo incompleto: arquivo obrigatorio indisponivel.\n' >&2
    exit 1
  fi
done
if [[ "$(sha256sum "$backup_file" | awk '{print $1}')" != "$backup_sha" ]]; then
  printf 'Hash do backup cifrado divergente; migration nao iniciada.\n' >&2
  exit 1
fi
if [[ "$(sha256sum "$migration_file" | awk '{print $1}')" != "$migration_sha" ]]; then
  printf 'Hash da migration 026 divergente; migration nao iniciada.\n' >&2
  exit 1
fi
if [[ "$(sha256sum "$ca_file" | awk '{print $1}')" != 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]]; then
  printf 'CA do Supabase ausente ou alterada; migration nao iniciada.\n' >&2
  exit 1
fi
linked_ref="$(tr -d '\r\n' < "$ref_file")"
if [[ ${#linked_ref} -ne 20 || "$linked_ref" != xoof*esgx ]]; then
  printf 'Projeto vinculado diferente do piloto; migration nao iniciada.\n' >&2
  exit 1
fi
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]]; then
  printf 'Formato do vinculo invalido; migration nao iniciada.\n' >&2
  exit 1
fi
if [[ "$PGDATABASE" != *"$linked_ref"* || "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo ou TLS divergente; migration nao iniciada.\n' >&2
  exit 1
fi
unset linked_ref
if ! docker image inspect postgres:17-alpine >/dev/null 2>&1; then
  printf 'Imagem PostgreSQL 17 local indisponivel; migration nao iniciada.\n' >&2
  exit 1
fi

read -r -s -p 'Senha do banco (nao aparece na tela): ' PGPASSWORD
printf '\n'
if [[ -z "$PGPASSWORD" ]]; then
  printf 'Senha vazia; migration nao iniciada.\n' >&2
  exit 1
fi
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full PGSSLROOTCERT=/run/supabase-ca.crt
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT' EXIT

# Catalog-only check: outputs three booleans, never rows, identifiers, or links.
PREFLIGHT_SQL="SELECT (to_regclass('public.biometrias') IS NOT NULL)::int,
 (to_regclass('public.jornadas_diarias') IS NOT NULL)::int,
 (to_regclass('public.politicas_biometricas') IS NULL)::int"
export PREFLIGHT_SQL
if ! preflight="$(docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PREFLIGHT_SQL \
    postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command "$PREFLIGHT_SQL"' \
    2>"$log_file")"; then
  chmod 600 "$log_file"
  printf 'Preflight falhou. Log privado preservado; nao compartilhe.\n' >&2
  exit 1
fi
if [[ "$preflight" =~ ^[01]\|[01]\|[01]$ ]]; then
  IFS='|' read -r has_biometrias has_025 missing_026 <<< "$preflight"
  printf 'Schema: biometria_base=%s; migration_025_presente=%s; migration_026_ausente=%s.\n' \
    "$has_biometrias" "$has_025" "$missing_026"
else
  printf 'Preflight retornou formato inesperado; migration nao iniciada.\n' >&2
  exit 1
fi
if [[ "${1:-}" == '--diagnose-schema' ]]; then
  printf 'Diagnostico somente leitura concluido; nenhuma migration iniciada.\n'
  exit 0
fi
if [[ "${1:-}" == '--diagnose-026-completeness' ]]; then
  CATALOG_SQL="SELECT
    (to_regclass('public.politicas_biometricas') IS NOT NULL
      AND to_regclass('public.perfis_tecnicos_biometricos') IS NOT NULL
      AND to_regclass('public.holds_biometricos') IS NOT NULL
      AND to_regclass('public.operacoes_biometricas') IS NOT NULL
      AND to_regclass('public.historico_ciclo_biometrico') IS NOT NULL)::int,
    (EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
      WHERE a.attrelid = 'public.biometrias'::regclass
        AND a.attname = 'politica_biometrica_id' AND NOT a.attisdropped)
      AND EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
      WHERE a.attrelid = 'public.biometrias'::regclass
        AND a.attname = 'perfil_tecnico_id' AND NOT a.attisdropped)
      AND EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
      WHERE a.attrelid = 'public.biometrias'::regclass
        AND a.attname = 'eliminacao_elegivel_at' AND NOT a.attisdropped))::int,
    (to_regclass('public.biometrias_uma_ativa_por_vinculo_idx') IS NOT NULL
      AND to_regclass('public.perfis_biometricos_um_ativo_idx') IS NOT NULL)::int,
    (EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t
      WHERE t.tgrelid = 'public.auditoria'::regclass
        AND t.tgname = 'auditoria_metadados_seguros' AND NOT t.tgisinternal)
      AND EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t
      WHERE t.tgrelid = to_regclass('public.historico_ciclo_biometrico')
        AND t.tgname = 'historico_biometrico_append_only' AND NOT t.tgisinternal))::int,
    (EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
      WHERE c.conrelid = 'public.biometrias'::regclass
        AND c.conname = 'biometrias_material_estado_check')
      AND EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
      WHERE c.conrelid = 'public.biometrias'::regclass
        AND c.conname = 'biometrias_politica_fk'))::int"
  export CATALOG_SQL
  if ! catalog_result="$(docker run --rm --pull=never --entrypoint sh \
      --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
      --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env CATALOG_SQL \
      postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command "$CATALOG_SQL"' \
      2>"$log_file")"; then
    chmod 600 "$log_file"
    printf 'Diagnostico de catalogo falhou; log privado preservado.\n' >&2
    exit 1
  fi
  if [[ ! "$catalog_result" =~ ^[01]\|[01]\|[01]\|[01]\|[01]$ ]]; then
    printf 'Diagnostico de catalogo retornou formato inesperado.\n' >&2
    exit 1
  fi
  IFS='|' read -r tables columns indexes triggers constraints <<< "$catalog_result"
  printf '026: tabelas=%s; colunas=%s; indices=%s; gatilhos=%s; restricoes=%s.\n' \
    "$tables" "$columns" "$indexes" "$triggers" "$constraints"
  printf 'Diagnostico somente leitura concluido; nenhuma migration iniciada.\n'
  exit 0
fi
if [[ "$preflight" != '1|1|1' ]]; then
  chmod 600 "$log_file"
  printf 'Schema nao esta exatamente no estado esperado (025 presente, 026 ausente). Migration nao iniciada.\n' >&2
  exit 1
fi

printf 'Alvo mascarado: xoof...esgx/main; TLS verify-full; backup cifrado confirmado.\n'
printf 'A migration 026 cria tabelas e indices, altera biometrias e auditoria.\n'
printf 'Pode bloquear escritas brevemente; nao ha downgrade automatico.\n'
read -r -p 'Digite APLICAR-026 para confirmar esta operacao no banco atual: ' confirmation
if [[ "$confirmation" != 'APLICAR-026' ]]; then
  printf 'Cancelado antes de executar SQL.\n'
  exit 0
fi

if docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --mount "type=bind,source=$migration_file,target=/run/migration-026.sql,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
    postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" --no-psqlrc --set=ON_ERROR_STOP=1 --file=/run/migration-026.sql' \
    >"$log_file" 2>&1; then
  chmod 600 "$log_file"
  printf 'Migration 026 concluida; log privado preservado. Nao compartilhe o log.\n'
else
  chmod 600 "$log_file"
  printf 'Migration 026 falhou. Transacao abortada; log privado preservado. Pare a publicacao.\n' >&2
  exit 1
fi
