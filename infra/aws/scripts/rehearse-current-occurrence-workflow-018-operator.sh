#!/usr/bin/env bash
set -euo pipefail
umask 077

# Operado privadamente: restaura somente public em destino local sem rede.
# Nunca conecta ao banco remoto nem imprime linhas do backup.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
repo_dir='/mnt/c/Users/lavin/Downloads/FrequenIA'
backup_name="${1:-}"
expected_sha="${2:-}"
if [[ "$PWD" != "$private_dir" || ! "$backup_name" =~ ^supabase-pilot-[0-9]{8}-[0-9]{6}\.dump\.gpg$ ||
      ! "$expected_sha" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'Informe nome e SHA-256 do backup novo, a partir da pasta privada.\n'; exit 1
fi
backup_file="$private_dir/$backup_name"
migration_file="$repo_dir/supabase/migrations/018_correction_manager_hr_workflow.sql"
migration_sha='4df3f2b03b2f2a81283e37b91e8cbe0a3d600de6652e5196800c07e4c4aaddbe'
[[ -r "$backup_file" && "$(sha256sum "$backup_file" | awk '{print $1}')" == "$expected_sha" ]] || exit 1
[[ "$(sha256sum "$migration_file" | awk '{print $1}')" == "$migration_sha" ]] || exit 1
age=$(( $(date +%s) - $(stat -c %Y "$backup_file") ))
if [[ $age -lt 0 || $age -gt 7200 ]]; then
  printf 'Exigido backup novo (ate duas horas).\n'; exit 1
fi
stamp="$(date -u +%Y%m%d%H%M%S)"
container="frequenia-workflow-018-rehearsal-$stamp"
database='frequenia_workflow_018_rehearsal'
log_file="$private_dir/workflow-018-rehearsal-$stamp.private.log"
evidence_file="$private_dir/workflow-018-rehearsal-$stamp.evidence.txt"
[[ ! -e "$log_file" && ! -e "$evidence_file" ]] || exit 1
mapfile -t migrations < <(find "$repo_dir/supabase/migrations" -maxdepth 1 -type f -name '[0-9][0-9][0-9]_*.sql' -printf '%f\n' | sort)
[[ ${#migrations[@]} -eq 26 && "${migrations[17]}" == 018_* && "${migrations[25]}" == 026_* ]] || exit 1
docker image inspect pgvector/pgvector:pg17 >/dev/null 2>&1 || exit 1
read -r -s -p 'Frase secreta do backup NOVO (nao aparece na tela): ' BACKUP_PASSPHRASE
printf '\n'
[[ -n "$BACKUP_PASSPHRASE" ]] || exit 1
created=0
cleanup() {
  unset BACKUP_PASSPHRASE
  if [[ "$created" == 1 ]]; then docker stop -t 15 "$container" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
if ! gpg --batch --pinentry-mode loopback --no-symkey-cache --passphrase-fd 3 \
  --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
  docker run --rm --pull=never --network none -i --entrypoint pg_restore pgvector/pgvector:pg17 --list >/dev/null 2>&1; then
  printf 'Backup ou frase invalida; ensaio nao iniciado.\n'; exit 1
fi
docker run -d --pull=never --name "$container" --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB="$database" pgvector/pgvector:pg17 >"$log_file" 2>&1
created=1
[[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" == none ]] || exit 1
[[ "$(docker inspect "$container" --format '{{json .HostConfig.PortBindings}}')" == '{}' ]] || exit 1
ready=0
for _attempt in $(seq 1 30); do
  if docker exec "$container" pg_isready -q -U postgres; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || { printf 'PostgreSQL isolado indisponivel.\n'; exit 1; }
for migration in "${migrations[@]}"; do
  [[ "$migration" == 018_* ]] && continue
  if ! docker exec -i "$container" psql -U postgres -d "$database" -X -q -v ON_ERROR_STOP=1 -f - \
    <"$repo_dir/supabase/migrations/$migration" >>"$log_file" 2>&1; then
    printf 'Preparo do schema falhou; destino e log preservados.\n'; exit 1
  fi
done
read -r -d '' restore_prefix <<'SQL' || true
\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT conrelid, conname FROM pg_constraint
  WHERE contype='f' AND connamespace='public'::regnamespace LOOP
  EXECUTE format('ALTER TABLE %s ALTER CONSTRAINT %I DEFERRABLE INITIALLY DEFERRED',item.conrelid::regclass,item.conname);
 END LOOP;
END $$;
SQL
read -r -d '' restore_suffix <<'SQL' || true
SET CONSTRAINTS ALL IMMEDIATE;
COMMIT;
SQL
set +e
(
  printf '%s\n' "$restore_prefix"
  gpg --batch --pinentry-mode loopback --no-symkey-cache --passphrase-fd 3 \
    --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>>"$log_file" |
    docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl --data-only --schema=public --file=-
  stream_status=("${PIPESTATUS[@]}")
  [[ "${stream_status[0]}" -eq 0 && "${stream_status[1]}" -eq 0 ]] || exit 41
  printf '%s\n' "$restore_suffix"
) 2>>"$log_file" | docker exec -i "$container" psql -U postgres -d "$database" -X -q -v ON_ERROR_STOP=1 -f - >>"$log_file" 2>&1
pipeline_status=("${PIPESTATUS[@]}")
set -e
if [[ "${pipeline_status[0]}" -ne 0 || "${pipeline_status[1]}" -ne 0 ]]; then
  printf 'Restore do backup novo falhou; Supabase nao alterado; log privado preservado.\n'; exit 1
fi
unset BACKUP_PASSPHRASE
census_sql='SELECT (SELECT count(*) FROM marcacoes),(SELECT count(*) FROM jornadas_diarias),(SELECT count(*) FROM biometrias),(SELECT count(*) FROM correcoes);'
before="$(docker exec "$container" psql -U postgres -d "$database" -X -q -t -A -v ON_ERROR_STOP=1 -c "$census_sql" 2>>"$log_file")"
[[ "$before" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]] || exit 1
if ! docker exec -i "$container" psql -U postgres -d "$database" -X -q -v ON_ERROR_STOP=1 -f - \
  <"$migration_file" >>"$log_file" 2>&1; then
  printf 'Migration 018 falhou na copia; Supabase nao alterado; log privado preservado.\n'; exit 1
fi
after="$(docker exec "$container" psql -U postgres -d "$database" -X -q -t -A -v ON_ERROR_STOP=1 -c "$census_sql" 2>>"$log_file")"
[[ "$before" == "$after" ]] || { printf 'Censo divergiu; interrompa a correcao remota.\n'; exit 1; }
check_sql="SELECT (EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='correcoes'::regclass AND conname='correcoes_estado_check' AND pg_get_constraintdef(oid) LIKE '%pendente_gestor%'))::int,(NOT EXISTS(SELECT 1 FROM correcoes WHERE estado IN ('solicitada','em_analise_gestor','em_analise_rh')))::int;"
checks="$(docker exec "$container" psql -U postgres -d "$database" -X -q -t -A -v ON_ERROR_STOP=1 -c "$check_sql" 2>>"$log_file")"
[[ "$checks" == '1|1' ]] || { printf 'Pos-condicoes falharam na copia.\n'; exit 1; }
printf 'backup=%s\nbackup_sha256=%s\nmigration_sha256=%s\ncontainer=%s\nvalidated_at=%s\nrestore=1\nmigration=1\ncounts_preserved=1\n' \
  "$backup_name" "$expected_sha" "$migration_sha" "$container" "$(date +%s)" >"$evidence_file"
printf 'ensaio_workflow_018: backup_restaurado=1; migration_aplicada_na_copia=1; contagens_preservadas=1; estados_compativeis=1.\n'
printf 'Evidencia: %s\n' "${evidence_file##*/}"
printf 'Supabase ativo nao alterado. Copia local sera parada e preservada.\n'
