#!/usr/bin/env bash
set -euo pipefail

container='frequenia-restore-20261024'
database='frequenia_restore_public_1'

if [[ "$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')" != none ]] ||
   [[ "$(docker inspect "$container" --format '{{json .NetworkSettings.Ports}}')" != '{}' ]]; then
  printf 'Container isolado nao confirmado; censo nao iniciado.\n' >&2
  exit 1
fi

docker start "$container" >/dev/null
trap 'docker stop -t 20 "$container" >/dev/null 2>&1 || true' EXIT
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

read -r -d '' CENSUS_SQL <<'SQL' || true
SELECT
  (SELECT count(*) FROM public.usuarios),
  (SELECT count(*) FROM public.empresas),
  (SELECT count(*) FROM public.funcionarios),
  (SELECT count(*) FROM public.biometrias),
  (SELECT count(*) FROM public.marcacoes),
  (SELECT count(*) FROM public.terminais_ponto),
  (SELECT count(*) FROM public.jornadas_diarias),
  (SELECT count(*) FROM public.tentativas_faciais),
  (SELECT count(*) FROM public.politicas_biometricas),
  (SELECT count(*) FROM public.perfis_tecnicos_biometricos);
SQL
if ! result="$(printf '%s\n' "$CENSUS_SQL" | docker exec -i "$container" \
    psql -U postgres -d "$database" --no-psqlrc --quiet --tuples-only \
    --no-align --set=ON_ERROR_STOP=1 --file=- 2>/dev/null)"; then
  printf 'Censo do backup isolado falhou; nenhuma linha foi exibida.\n' >&2
  exit 1
fi
if [[ ! "$result" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]]; then
  printf 'Censo do backup retornou formato inesperado.\n' >&2
  exit 1
fi
IFS='|' read -r users companies employees biometrics markings terminals journeys attempts policies profiles <<< "$result"
printf 'backup_censo: usuarios=%s; empresas=%s; funcionarios=%s; biometrias=%s; marcacoes=%s; terminais=%s; jornadas=%s; tentativas_faciais=%s; politicas=%s; perfis=%s.\n' \
  "$users" "$companies" "$employees" "$biometrics" "$markings" "$terminals" "$journeys" "$attempts" "$policies" "$profiles"
