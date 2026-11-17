#!/usr/bin/env bash
set -euo pipefail
umask 077

# Catalog metadata only. No participant rows or secret values are returned.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
ref_file="$private_dir/supabase/.temp/project-ref"
url_file="$private_dir/supabase/.temp/pooler-url"
ca_file="$private_dir/supabase-prod-ca-2021.crt"
log_file="$private_dir/occurrence-schema-$(date +%Y%m%d-%H%M%S).private.log"
[[ "$PWD" == "$private_dir" ]] || { printf 'Execute na pasta privada.\n'; exit 1; }
for file in "$ref_file" "$url_file" "$ca_file"; do
  [[ -r "$file" ]] || { printf 'Vinculo privado incompleto.\n'; exit 1; }
done
[[ "$(sha256sum "$ca_file" | awk '{print $1}')" == 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]] || exit 1
linked_ref="$(tr -d '\r\n' < "$ref_file")"
[[ ${#linked_ref} -eq 20 && "$linked_ref" == xoof*esgx ]] || exit 1
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]] ||
   [[ "$PGDATABASE" != *"$linked_ref"* || "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo privado invalido.\n'; exit 1
fi
unset linked_ref
read -r -s -p 'Senha do banco (nao aparece na tela): ' PGPASSWORD
printf '\n'
[[ -n "$PGPASSWORD" ]] || exit 1
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full PGSSLROOTCERT=/run/supabase-ca.crt PGCONNECT_TIMEOUT=8
trap 'unset PGDATABASE PGPASSWORD DIAGNOSTIC_SQL' EXIT
read -r -d '' DIAGNOSTIC_SQL <<'SQL' || true
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
WITH required_columns(table_name, column_name) AS (VALUES
 ('ocorrencias','primeira_ocorrencia_at'), ('ocorrencias','marcacao_id'),
 ('correcoes','ocorrencia_id'), ('correcoes','categoria'),
 ('correcoes','tipo_marcacao_proposto'), ('correcoes','solicitante_usuario_id'),
 ('auditoria','metadados'), ('auditoria','entidade_id')),
relations AS (SELECT c.oid, c.relname, c.relrowsecurity
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN ('ocorrencias','correcoes','auditoria'))
SELECT
 (SELECT count(*)=3 FROM relations)::int,
 (NOT EXISTS (SELECT 1 FROM required_columns r WHERE NOT EXISTS (
   SELECT 1 FROM information_schema.columns c WHERE c.table_schema='public'
    AND c.table_name=r.table_name AND c.column_name=r.column_name)))::int,
 (EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=to_regclass('public.correcoes')
   AND conname='correcoes_estado_check' AND pg_get_constraintdef(oid) LIKE '%pendente_gestor%'))::int,
 (SELECT coalesce(bool_and(has_table_privilege(oid,'INSERT')),false) FROM relations)::int,
 (SELECT coalesce(bool_and(has_table_privilege(oid,'SELECT')),false) FROM relations)::int,
 (SELECT coalesce(bool_and(NOT relrowsecurity OR (SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname=current_user)),false) FROM relations)::int,
 (EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=to_regclass('public.correcoes')
   AND contype='c' AND pg_get_constraintdef(oid) LIKE '%em_analise_gestor%'
   AND pg_get_constraintdef(oid) NOT LIKE '%pendente_gestor%'))::int,
 (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
   AND table_name='correcoes' AND column_name='estado' AND column_default LIKE '%pendente_gestor%'))::int,
 (EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=to_regclass('public.correcoes')
   AND conname='correcoes_decisao_estado_check'))::int,
 (to_regclass('public.correcoes_empresa_estado_data_idx') IS NOT NULL)::int;
ROLLBACK;
SQL
export DIAGNOSTIC_SQL
: >"$log_file"
status=1
for attempt in 1 2 3; do
set +e
result="$(docker run --rm --pull=never --entrypoint sh \
 --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
 --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PGCONNECT_TIMEOUT --env DIAGNOSTIC_SQL \
 postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command="$DIAGNOSTIC_SQL"' 2>>"$log_file")"
status=$?
set -e
[[ $status -eq 0 ]] && break
if [[ $attempt -lt 3 ]] && grep -Eqi 'could not translate host name|Name or service not known|temporary failure in name resolution|connection timed out|Network is unreachable|No route to host' "$log_file"; then
 printf 'Conexao temporariamente indisponivel; repetindo consulta somente leitura.\n'
 sleep 2
else
 break
fi
done
chmod 600 "$log_file"
if [[ $status -ne 0 || ! "$result" =~ ^[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]$ ]]; then
 printf 'Diagnostico de estrutura falhou; log privado preservado.\n'; exit 1
fi
IFS='|' read -r tables columns workflow insert select rls_bypass legacy default_current decision index_current <<<"$result"
printf 'ocorrencia_schema: tabelas=%s; colunas=%s; workflow=%s; permissao_insert=%s; permissao_select=%s; rls_bypass=%s.\n' "$tables" "$columns" "$workflow" "$insert" "$select" "$rls_bypass"
printf 'ocorrencia_workflow: restricao_legada=%s; padrao_atual=%s; decisao_atual=%s; indice_atual=%s.\n' "$legacy" "$default_current" "$decision" "$index_current"
printf 'Somente catalogo de estrutura consultado; nenhuma linha pessoal acessada.\n'
