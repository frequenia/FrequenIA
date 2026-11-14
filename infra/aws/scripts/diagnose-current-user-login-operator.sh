#!/usr/bin/env bash
set -euo pipefail
umask 077

# Diagnostico privado e somente leitura. Nunca imprime CPF, e-mail, hash,
# identificador ou linha pessoal.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
ref_file="$private_dir/supabase/.temp/project-ref"
url_file="$private_dir/supabase/.temp/pooler-url"
ca_file="$private_dir/supabase-prod-ca-2021.crt"

if [[ "$PWD" != "$private_dir" ]]; then
  printf 'Execute a partir da pasta privada de backup.\n' >&2
  exit 1
fi
for file in "$ref_file" "$url_file" "$ca_file"; do
  if [[ ! -r "$file" ]]; then
    printf 'Vinculo privado incompleto; diagnostico nao iniciado.\n' >&2
    exit 1
  fi
done
if [[ "$(sha256sum "$ca_file" | awk '{print $1}')" != 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]]; then
  printf 'CA publica ausente ou alterada; diagnostico nao iniciado.\n' >&2
  exit 1
fi

linked_ref="$(tr -d '\r\n' < "$ref_file")"
if [[ ${#linked_ref} -ne 20 || "$linked_ref" != xoof*esgx ]]; then
  printf 'Projeto vinculado diferente do piloto; diagnostico nao iniciado.\n' >&2
  exit 1
fi
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]] || \
   [[ "$PGDATABASE" != *"$linked_ref"* ]] || \
   [[ "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo privado invalido; diagnostico nao iniciado.\n' >&2
  exit 1
fi
unset linked_ref
if ! docker image inspect postgres:17-alpine >/dev/null 2>&1; then
  printf 'Imagem PostgreSQL local indisponivel; diagnostico nao iniciado.\n' >&2
  exit 1
fi

read -r -s -p 'Senha do banco (nao aparece na tela): ' PGPASSWORD
printf '\n'
if [[ "${1:-}" == '--census' ]]; then
  export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
  export PGSSLROOTCERT=/run/supabase-ca.crt
  trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT' EXIT
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
  export CENSUS_SQL
  if ! census="$(docker run --rm --pull=never --entrypoint sh \
      --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
      --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
      --env CENSUS_SQL postgres:17-alpine -c \
        'printf "%s\n" "$CENSUS_SQL" | exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-' \
      2>/dev/null)"; then
    printf 'Censo falhou; nenhuma linha foi exibida.\n' >&2
    exit 1
  fi
  if [[ ! "$census" =~ ^[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+\|[0-9]+$ ]]; then
    printf 'Censo retornou formato inesperado; nenhuma linha foi exibida.\n' >&2
    exit 1
  fi
  IFS='|' read -r users companies employees biometrics markings terminals journeys attempts <<< "$census"
  printf 'censo: usuarios=%s; empresas=%s; funcionarios=%s; biometrias=%s; marcacoes=%s; terminais=%s; jornadas=%s; tentativas_faciais=%s.\n' \
    "$users" "$companies" "$employees" "$biometrics" "$markings" "$terminals" "$journeys" "$attempts"
  printf 'Censo agregado somente leitura concluido.\n'
  exit 0
fi
read -r -s -p 'CPF da propria conta (nao aparece na tela): ' DIAG_CPF
printf '\n'
read -r -s -p 'E-mail cadastrado (nao aparece na tela): ' DIAG_EMAIL
printf '\n'
DIAG_CPF="$(printf '%s' "$DIAG_CPF" | tr -cd '0-9')"
if [[ -z "$PGPASSWORD" || ! "$DIAG_CPF" =~ ^[0-9]{11}$ ||
      ${#DIAG_EMAIL} -gt 254 || "$DIAG_EMAIL" != *@* ||
      "$DIAG_EMAIL" == *$'\n'* || "$DIAG_EMAIL" == *$'\r'* ]]; then
  printf 'Entrada privada invalida; diagnostico nao iniciado.\n' >&2
  exit 1
fi
DIAG_EMAIL_B64="$(printf '%s' "$DIAG_EMAIL" | base64 | tr -d '\r\n')"
unset DIAG_EMAIL

export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/supabase-ca.crt DIAG_CPF DIAG_EMAIL_B64
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT DIAG_CPF DIAG_EMAIL DIAG_EMAIL_B64' EXIT

read -r -d '' DIAG_SQL <<'SQL' || true
WITH alvo AS (
  SELECT id, status, senha_hash, perfil_sistema
  FROM public.usuarios
  WHERE cpf = '__PRIVATE_CPF__'
), alvo_email AS (
  SELECT id, cpf, status, senha_hash, perfil_sistema
  FROM public.usuarios
  WHERE lower(email) = lower(convert_from(decode('__PRIVATE_EMAIL_B64__', 'base64'), 'UTF8'))
), indicadores AS (
  SELECT
    EXISTS (SELECT 1 FROM alvo) AS usuario_existe,
    EXISTS (SELECT 1 FROM alvo_email) AS email_existe,
    EXISTS (
      SELECT 1 FROM alvo_email WHERE cpf = '__PRIVATE_CPF__'
    ) AS email_cpf_corresponde,
    EXISTS (SELECT 1 FROM alvo_email WHERE status = 'ativo') AS usuario_ativo,
    EXISTS (
      SELECT 1 FROM alvo_email
      WHERE senha_hash IS NOT NULL AND btrim(senha_hash) <> ''
    ) AS senha_definida,
    EXISTS (
      SELECT 1 FROM alvo_email WHERE perfil_sistema = 'administrador_geral'
      UNION ALL
      SELECT 1
      FROM alvo_email a
      JOIN public.funcionarios f ON f.usuario_id = a.id
      JOIN public.empresas e ON e.id = f.empresa_id
      WHERE f.status = 'ativo' AND e.status = 'ativa'
    ) AS acesso_ativo,
    EXISTS (
      SELECT 1 FROM alvo_email WHERE perfil_sistema = 'administrador_geral'
      UNION ALL
      SELECT 1
      FROM alvo_email a
      JOIN public.funcionarios f ON f.usuario_id = a.id
      JOIN public.empresas e ON e.id = f.empresa_id
      WHERE f.status = 'ativo' AND e.status = 'ativa'
        AND f.perfil IN ('administrador', 'rh')
    ) AS acesso_admin_ou_rh
)
SELECT usuario_existe::int, email_existe::int, email_cpf_corresponde::int,
       usuario_ativo::int, senha_definida::int,
       acesso_ativo::int, acesso_admin_ou_rh::int
FROM indicadores;
SQL
export DIAG_SQL

set +e
diagnostic_output="$(docker run --rm --pull=never --entrypoint sh \
    --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
    --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
    --env DIAG_CPF --env DIAG_EMAIL_B64 --env DIAG_SQL \
    postgres:17-alpine -c \
      'query="$(printf "%s" "$DIAG_SQL" | sed "s|__PRIVATE_CPF__|$DIAG_CPF|g; s|__PRIVATE_EMAIL_B64__|$DIAG_EMAIL_B64|g")"; printf "%s\n" "$query" | exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-' \
    2>&1)"
diagnostic_status=$?
set -e
if [[ $diagnostic_status -ne 0 ]]; then
  case "$diagnostic_output" in
    *'password authentication failed'*|*'no password supplied'*|*'SASL'*|*'SCRAM'*)
      failure='autenticacao_banco' ;;
    *'certificate'*|*'root certificate'*|*'SSL error'*)
      failure='tls' ;;
    *'could not translate host name'*|*'Name or service not known'*)
      failure='dns' ;;
    *'Connection refused'*|*'connection timed out'*|*'Network is unreachable'*)
      failure='rede' ;;
    *'permission denied'*|*'insufficient privilege'*)
      failure='permissao_banco' ;;
    *'does not exist'*|*'syntax error'*)
      failure='schema_ou_consulta' ;;
    *) failure='nao_classificada' ;;
  esac
  printf 'Diagnostico falhou: tipo=%s; nenhuma linha foi exibida.\n' "$failure" >&2
  exit 1
fi
result="$diagnostic_output"
unset diagnostic_output
if [[ ! "$result" =~ ^[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]$ ]]; then
  printf 'Diagnostico retornou formato inesperado; nenhuma linha foi exibida.\n' >&2
  exit 1
fi
IFS='|' read -r exists email_exists cpf_matches active password access admin <<< "$result"
printf 'cadastro: cpf_existe=%s; email_existe=%s; email_cpf_corresponde=%s; usuario_ativo=%s; senha_definida=%s; acesso_ativo=%s; acesso_admin_ou_rh=%s.\n' \
  "$exists" "$email_exists" "$cpf_matches" "$active" "$password" "$access" "$admin"
printf 'Diagnostico somente leitura concluido.\n'
