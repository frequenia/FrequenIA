#!/usr/bin/env bash
set -euo pipefail
umask 077

# Diagnostico privado e somente leitura para um titular que opera a propria conta.
# Nunca exibe CPF, IDs, nomes, matricula, biometria ou linhas pessoais.
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
ref_file="$private_dir/supabase/.temp/project-ref"
url_file="$private_dir/supabase/.temp/pooler-url"
ca_file="$private_dir/supabase-prod-ca-2021.crt"
log_file="$private_dir/clock-conflict-diagnostic-$(TZ=America/Sao_Paulo date +%Y%m%d-%H%M%S).private.log"

if [[ "$PWD" != "$private_dir" ]]; then
  printf 'Execute este operador a partir da pasta privada de backup.\n' >&2
  exit 1
fi
for file in "$ref_file" "$url_file" "$ca_file"; do
  [[ -r "$file" ]] || { printf 'Vinculo privado incompleto.\n' >&2; exit 1; }
done
if [[ "$(sha256sum "$ca_file" | awk '{print $1}')" != 700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7 ]]; then
  printf 'CA publica ausente ou alterada.\n' >&2
  exit 1
fi
linked_ref="$(tr -d '\r\n' < "$ref_file")"
if [[ ${#linked_ref} -ne 20 || "$linked_ref" != xoof*esgx ]]; then
  printf 'Projeto vinculado diferente do piloto.\n' >&2
  exit 1
fi
IFS= read -r PGDATABASE < "$url_file" || [[ -n "${PGDATABASE:-}" ]]
PGDATABASE="${PGDATABASE%$'\r'}"
if [[ "$PGDATABASE" != postgresql://* && "$PGDATABASE" != postgres://* ]] ||
   [[ "$PGDATABASE" != *"$linked_ref"* ]] ||
   [[ "$PGDATABASE" == *sslmode=* || "$PGDATABASE" == *sslrootcert=* ]]; then
  printf 'Vinculo privado invalido.\n' >&2
  exit 1
fi
unset linked_ref

read -r -s -p 'Senha do banco (nao aparece na tela): ' PGPASSWORD
printf '\n'
read -r -s -p 'CPF da propria conta (nao aparece na tela): ' ACCOUNT_CPF
printf '\n'
if [[ -z "$PGPASSWORD" || ! "$ACCOUNT_CPF" =~ ^[0-9]{11}$ ]]; then
  printf 'Credencial ausente ou CPF invalido; diagnostico nao iniciado.\n' >&2
  exit 1
fi
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/supabase-ca.crt ACCOUNT_CPF
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT ACCOUNT_CPF DIAGNOSTIC_SQL' EXIT

read -r -d '' DIAGNOSTIC_SQL <<'SQL' || true
WITH alvo AS (
  SELECT f.id AS funcionario_id, f.empresa_id
  FROM usuarios u
  JOIN funcionarios f ON f.usuario_id=u.id
  WHERE u.cpf=current_setting('app.diagnostic_cpf', true)
    AND u.status='ativo' AND f.status='ativo'
  ORDER BY f.created_at DESC LIMIT 1
), hoje AS (
  SELECT (clock_timestamp() AT TIME ZONE 'America/Sao_Paulo')::date AS dia
), atribuicao AS (
  SELECT ft.id, ft.turno_id
  FROM alvo a CROSS JOIN hoje h
  JOIN funcionarios_turnos ft ON ft.empresa_id=a.empresa_id
    AND ft.funcionario_id=a.funcionario_id
    AND ft.vigencia_inicio<=h.dia
    AND (ft.vigencia_fim IS NULL OR ft.vigencia_fim>=h.dia)
  JOIN turnos t ON t.id=ft.turno_id AND t.empresa_id=ft.empresa_id AND t.status='ativo'
  ORDER BY ft.vigencia_inicio DESC, ft.created_at DESC LIMIT 1
), ultima_jornada AS (
  SELECT j.origem
  FROM alvo a CROSS JOIN hoje h
  JOIN jornadas_diarias j ON j.empresa_id=a.empresa_id
    AND j.funcionario_id=a.funcionario_id AND j.data_operacional=h.dia
  LIMIT 1
), ultima_tentativa AS (
  SELECT tj.resultado,
    CASE tj.motivo_codigo
      WHEN 'evento_confirmado' THEN 'evento_confirmado'
      WHEN 'jornada_nao_configurada' THEN 'jornada_nao_configurada'
      WHEN 'folga_programada' THEN 'folga_programada'
      WHEN 'jornada_concluida' THEN 'jornada_concluida'
      WHEN 'sem_evento_esperado' THEN 'sem_evento_esperado'
      WHEN 'tipo_legado_divergente' THEN 'tipo_legado_divergente'
      WHEN 'marcacao_recente' THEN 'marcacao_recente'
      ELSE 'outro'
    END AS motivo
  FROM alvo a
  JOIN tentativas_jornada tj ON tj.empresa_id=a.empresa_id
    AND tj.funcionario_id=a.funcionario_id
  ORDER BY tj.created_at DESC, tj.id DESC LIMIT 1
), ultima_facial AS (
  SELECT tf.resultado,
    CASE tf.motivo_codigo
      WHEN 'match' THEN 'match'
      WHEN 'biometria_ausente' THEN 'biometria_ausente'
      WHEN 'liveness_reprovado' THEN 'liveness_reprovado'
      WHEN 'nao_corresponde' THEN 'nao_corresponde'
      ELSE 'outro'
    END AS motivo
  FROM alvo a
  JOIN tentativas_faciais tf ON tf.empresa_id=a.empresa_id
    AND tf.funcionario_id=a.funcionario_id
  ORDER BY tf.created_at DESC, tf.id DESC LIMIT 1
)
SELECT
  (EXISTS (SELECT 1 FROM alvo))::int,
  (EXISTS (SELECT 1 FROM alvo a JOIN biometrias b ON b.empresa_id=a.empresa_id AND b.funcionario_id=a.funcionario_id WHERE b.status='ativa'))::int,
  (EXISTS (SELECT 1 FROM atribuicao))::int,
  (EXISTS (SELECT 1 FROM atribuicao at CROSS JOIN hoje h JOIN periodos_turno p ON p.turno_id=at.turno_id AND p.dia_semana=extract(dow FROM h.dia)::int))::int,
  coalesce((SELECT CASE origem WHEN 'sem_jornada' THEN 'sem_jornada' WHEN 'folga' THEN 'folga' ELSE 'configurada' END FROM ultima_jornada),'ausente'),
  coalesce((SELECT resultado FROM ultima_facial),'ausente'),
  coalesce((SELECT motivo FROM ultima_facial),'ausente'),
  coalesce((SELECT resultado FROM ultima_tentativa),'ausente'),
  coalesce((SELECT motivo FROM ultima_tentativa),'ausente');
SQL
export DIAGNOSTIC_SQL

set +e
result="$(docker run --rm --pull=never --entrypoint sh \
  --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
  --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
  --env ACCOUNT_CPF --env DIAGNOSTIC_SQL postgres:17-alpine -c \
  'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command="SET app.diagnostic_cpf TO '\''$ACCOUNT_CPF'\''; $DIAGNOSTIC_SQL"' \
  2>"$log_file")"
status=$?
set -e
chmod 600 "$log_file"
if [[ $status -ne 0 ]]; then
  printf 'Diagnostico falhou; nenhum dado foi exibido.\n' >&2
  exit 1
fi
if [[ ! "$result" =~ ^[01]\|[01]\|[01]\|[01]\|(ausente|sem_jornada|folga|configurada)\|(ausente|sucesso|falha|bloqueada|expirada)\|(ausente|match|biometria_ausente|liveness_reprovado|nao_corresponde|outro)\|(ausente|confirmada|analise|bloqueada)\|(ausente|evento_confirmado|jornada_nao_configurada|folga_programada|jornada_concluida|sem_evento_esperado|tipo_legado_divergente|marcacao_recente|outro)$ ]]; then
  printf 'Diagnostico retornou formato inesperado; nenhuma linha foi exibida.\n' >&2
  exit 1
fi
IFS='|' read -r conta biometria atribuicao periodo jornada facial_resultado facial_motivo jornada_resultado jornada_motivo <<<"$result"
printf 'clock_diag: conta_ativa=%s; biometria_ativa=%s; atribuicao_vigente=%s; periodo_hoje=%s; jornada_hoje=%s; facial_resultado=%s; facial_motivo=%s; jornada_resultado=%s; jornada_motivo=%s.\n' \
  "$conta" "$biometria" "$atribuicao" "$periodo" "$jornada" "$facial_resultado" "$facial_motivo" "$jornada_resultado" "$jornada_motivo"
printf 'Diagnostico somente leitura concluido.\n'
