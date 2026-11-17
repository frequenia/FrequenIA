#!/usr/bin/env bash
set -euo pipefail
umask 077

# Somente apos aprovacao especifica. Exige evidencia do backup novo restaurado.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
repo_dir='/mnt/c/Users/lavin/Downloads/FrequenIA'
evidence_name="${1:-}"
if [[ "$PWD" != "$private_dir" || ! "$evidence_name" =~ ^workflow-018-rehearsal-[0-9]{14}\.evidence\.txt$ ]]; then
  printf 'Informe a evidencia do ensaio aprovado, na pasta privada.\n'; exit 1
fi
evidence="$private_dir/$evidence_name"
[[ -r "$evidence" ]] || exit 1
field() { sed -n "s/^$1=//p" "$evidence"; }
backup_name="$(field backup)"
backup_sha="$(field backup_sha256)"
validated_at="$(field validated_at)"
container="$(field container)"
migration_sha='4df3f2b03b2f2a81283e37b91e8cbe0a3d600de6652e5196800c07e4c4aaddbe'
migration_file="$repo_dir/supabase/migrations/018_correction_manager_hr_workflow.sql"
[[ "$backup_name" =~ ^supabase-pilot-[0-9]{8}-[0-9]{6}\.dump\.gpg$ && "$backup_sha" =~ ^[0-9a-f]{64}$ ]] || exit 1
# Synthetic fixture evidence is deliberately ineligible for a remote migration.
[[ "$backup_name" != supabase-pilot-20000101-* ]] || exit 1
[[ "$validated_at" =~ ^[0-9]{10}$ && "$container" =~ ^frequenia-workflow-018-rehearsal-[0-9]{14}$ ]] || exit 1
[[ "$(field migration_sha256)" == "$migration_sha" && "$(field restore)" == 1 && "$(field migration)" == 1 && "$(field counts_preserved)" == 1 ]] || exit 1
age=$(( $(date +%s) - validated_at ))
[[ $age -ge 0 && $age -le 7200 ]] || { printf 'Ensaio vencido; refaca o backup e ensaio.\n'; exit 1; }
[[ "$(sha256sum "$private_dir/$backup_name" | awk '{print $1}')" == "$backup_sha" ]] || exit 1
[[ "$(sha256sum "$migration_file" | awk '{print $1}')" == "$migration_sha" ]] || exit 1
[[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" == none && "$(docker inspect "$container" --format '{{.State.Running}}')" == false ]] || exit 1
ref_file="$private_dir/supabase/.temp/project-ref"
url_file="$private_dir/supabase/.temp/pooler-url"
ca_file="$private_dir/supabase-prod-ca-2021.crt"
[[ "$(sha256sum "$ca_file" | awk '{print $1}')" == 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]] || exit 1
linked_ref="$(tr -d '\r\n' <"$ref_file")"
[[ ${#linked_ref} -eq 20 && "$linked_ref" == xoof*esgx ]] || exit 1
IFS= read -r PGDATABASE <"$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]] ||
   [[ "$PGDATABASE" != *"$linked_ref"* || "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then exit 1; fi
unset linked_ref
log_file="$private_dir/workflow-018-apply-$(date -u +%Y%m%d%H%M%S).private.log"
[[ ! -e "$log_file" ]] || exit 1
read -r -s -p 'Senha do banco ativo (nao aparece na tela): ' PGPASSWORD
printf '\n'
[[ -n "$PGPASSWORD" ]] || exit 1
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full PGSSLROOTCERT=/run/supabase-ca.crt PGCONNECT_TIMEOUT=8
export PGOPTIONS='-c lock_timeout=5s -c statement_timeout=60s'
trap 'unset PGDATABASE PGPASSWORD PGOPTIONS CHECK_SQL' EXIT
remote_query() {
  docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PGCONNECT_TIMEOUT --env PGOPTIONS --env CHECK_SQL \
    postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" -X -q -t -A -v ON_ERROR_STOP=1 -c "$CHECK_SQL"' 2>>"$log_file"
}
CHECK_SQL="SELECT
 (EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid=to_regclass('public.correcoes') AND conname='correcoes_estado_check' AND pg_get_constraintdef(oid) LIKE '%em_analise_gestor%' AND pg_get_constraintdef(oid) NOT LIKE '%pendente_gestor%'))::int,
 (EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='correcoes' AND column_name='estado' AND column_default LIKE '%solicitada%'))::int,
 (NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid=to_regclass('public.correcoes') AND conname='correcoes_decisao_estado_check'))::int,
 (to_regclass('public.correcoes_empresa_estado_data_idx') IS NULL)::int;"
export CHECK_SQL
if ! preflight="$(remote_query)" || [[ "$preflight" != '1|1|1|1' ]]; then
  printf 'Preflight remoto divergente ou indisponivel; migration nao iniciada.\n'; exit 1
fi
printf 'Alvo: xoof...esgx/main; TLS verify-full; backup novo restaurado em isolamento.\n'
printf 'Migration 018: workflow de correcoes; espera por lock ate 5s, cada instrucao ate 60s.\n'
printf 'A transacao pode bloquear gravacoes brevemente.\n'
printf 'Nao altera marcacoes, jornadas, biometria, politica ou perfil. Sem downgrade automatico.\n'
read -r -p 'Digite APLICAR-WORKFLOW-018 para confirmar: ' confirmation
if [[ "$confirmation" != APLICAR-WORKFLOW-018 ]]; then printf 'Cancelado; nenhuma migration iniciada.\n'; exit 0; fi
if ! docker run --rm --pull=never --entrypoint sh \
  --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
  --mount "type=bind,source=$migration_file,target=/run/workflow-018.sql,readonly" \
  --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT --env PGCONNECT_TIMEOUT --env PGOPTIONS \
  postgres:17-alpine -c 'exec psql --dbname="$PGDATABASE" -X -q -v ON_ERROR_STOP=1 -f /run/workflow-018.sql' >>"$log_file" 2>&1; then
  printf 'Migration falhou; transacao abortada. Preserve backup e log privado.\n'; exit 1
fi
CHECK_SQL="SELECT
 (EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.correcoes'::regclass AND conname='correcoes_estado_check' AND pg_get_constraintdef(oid) LIKE '%pendente_gestor%'))::int,
 (EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='correcoes' AND column_name='estado' AND column_default LIKE '%pendente_gestor%'))::int,
 (EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.correcoes'::regclass AND conname='correcoes_decisao_estado_check'))::int,
 (to_regclass('public.correcoes_empresa_estado_data_idx') IS NOT NULL)::int;"
if ! postflight="$(remote_query)" || [[ "$postflight" != '1|1|1|1' ]]; then
  printf 'Migration com commit, mas pos-validacao falhou. Pare os testes; nao execute downgrade.\n'; exit 1
fi
printf 'workflow_018: migration_aplicada=1; restricao_atual=1; padrao_atual=1; decisao_atual=1; indice_atual=1.\n'
printf 'Backup e copia de ensaio preservados. Teste funcional ainda pendente.\n'
