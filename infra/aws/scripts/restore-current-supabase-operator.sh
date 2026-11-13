#!/usr/bin/env bash
set -euo pipefail

# The operator runs this privately. Never print the passphrase, decrypted dump,
# SQL diagnostics, or any database row. Keep the isolated container on failure.
backup_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
backup_file="$backup_dir/supabase-pilot-20261024-164527.dump.gpg"
expected_sha='b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f'
container='frequenia-restore-20261024'
image='pgvector/pgvector:pg17'

if [[ "$PWD" != "$backup_dir" || ! -r "$backup_file" ]]; then
  printf 'Pasta privada ou backup nao encontrado; restore nao iniciado.\n' >&2
  exit 1
fi
if [[ "$(sha256sum "$backup_file" | awk '{print $1}')" != "$expected_sha" ]]; then
  printf 'Hash do backup diverge; restore nao iniciado.\n' >&2
  exit 1
fi
if docker container inspect "$container" >/dev/null 2>&1; then
  printf 'Container de restore ja existe; nada foi sobrescrito.\n' >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  printf 'Imagem PostgreSQL/pgvector local ausente; restore nao iniciado.\n' >&2
  exit 1
fi
free_kib="$(df -Pk "$backup_dir" | awk 'NR == 2 { print $4 }')"
if [[ ! "$free_kib" =~ ^[0-9]+$ || "$free_kib" -lt 614400 ]]; then
  printf 'Espaco livre insuficiente (minimo: 600 MiB); restore nao iniciado.\n' >&2
  exit 1
fi

umask 077
read -r -s -p 'Frase secreta do backup (nao aparece na tela): ' BACKUP_PASSPHRASE
printf '\n'
if [[ -z "$BACKUP_PASSPHRASE" ]]; then
  printf 'Frase secreta vazia; restore nao iniciado.\n' >&2
  exit 1
fi
trap 'unset BACKUP_PASSPHRASE' EXIT

if ! docker run -d --pull=never --name "$container" --network none \
    --env POSTGRES_HOST_AUTH_METHOD=trust "$image" >/dev/null 2>&1; then
  printf 'Nao foi possivel criar o container isolado; nenhum dado restaurado.\n' >&2
  exit 1
fi
printf 'Container isolado criado, sem rede e sem porta publicada.\n'

ready=0
for ((attempt=0; attempt<30; attempt++)); do
  if docker exec "$container" pg_isready -q -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  printf 'PostgreSQL nao ficou pronto; container preservado.\n' >&2
  exit 1
fi

if ! gpg --batch --yes --pinentry-mode loopback --no-symkey-cache \
    --passphrase-fd 3 --decrypt "$backup_file" 3<<<"$BACKUP_PASSPHRASE" 2>/dev/null |
    docker exec -i "$container" pg_restore --exit-on-error --no-owner --no-acl \
      --dbname=postgres -U postgres 2>/dev/null; then
  printf 'Restore nao concluiu. Container e backup preservados; nenhuma linha exibida.\n' >&2
  exit 1
fi

if ! docker exec "$container" psql -U postgres -d postgres \
    --no-psqlrc --quiet --tuples-only --no-align \
    --command "SELECT count(*) FROM pg_class WHERE relkind IN ('r','p')" \
    >/dev/null 2>&1; then
  printf 'Restore concluiu, mas a checagem de catalogo falhou; container preservado.\n' >&2
  exit 1
fi
printf 'Restore concluiu com exit code zero; checagem de catalogo passou.\n'
printf 'Container isolado preservado: %s\n' "$container"
printf 'Backup original preservado; nenhum recurso AWS ou Supabase foi alterado.\n'
