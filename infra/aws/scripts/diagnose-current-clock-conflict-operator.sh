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
read -r -s -p 'Matricula digitada no quiosque (nao aparece na tela): ' ACCOUNT_REGISTRATION
printf '\n'
read -r -s -p 'Credencial ativada nesta guia (nao aparece na tela): ' TERMINAL_CREDENTIAL
printf '\n'
ACCOUNT_CPF="$(printf '%s' "$ACCOUNT_CPF" | tr -cd '0-9')"
if [[ -z "$PGPASSWORD" || ! "$ACCOUNT_CPF" =~ ^[0-9]{11}$ ||
      -z "$ACCOUNT_REGISTRATION" || ${#ACCOUNT_REGISTRATION} -gt 128 ||
      "$ACCOUNT_REGISTRATION" == *$'\n'* || "$ACCOUNT_REGISTRATION" == *$'\r'* ||
      ${#TERMINAL_CREDENTIAL} -lt 32 || ${#TERMINAL_CREDENTIAL} -gt 256 ||
      "$TERMINAL_CREDENTIAL" == *$'\n'* || "$TERMINAL_CREDENTIAL" == *$'\r'* ]]; then
  printf 'Credencial ou identificador invalido; diagnostico nao iniciado.\n' >&2
  exit 1
fi
ACCOUNT_REGISTRATION_B64="$(printf '%s' "$ACCOUNT_REGISTRATION" | base64 | tr -d '\r\n')"
TERMINAL_CREDENTIAL_HASH="$(printf '%s' "$TERMINAL_CREDENTIAL" | sha256sum | awk '{print $1}')"
unset ACCOUNT_REGISTRATION
unset TERMINAL_CREDENTIAL
export PGDATABASE PGPASSWORD PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/supabase-ca.crt ACCOUNT_CPF ACCOUNT_REGISTRATION_B64 TERMINAL_CREDENTIAL_HASH
trap 'unset PGDATABASE PGPASSWORD PGSSLMODE PGSSLROOTCERT ACCOUNT_CPF ACCOUNT_REGISTRATION ACCOUNT_REGISTRATION_B64 TERMINAL_CREDENTIAL TERMINAL_CREDENTIAL_HASH DIAGNOSTIC_SQL' EXIT

read -r -d '' DIAGNOSTIC_SQL <<'SQL' || true
WITH vinculos AS (
  SELECT f.id AS funcionario_id, f.empresa_id, f.matricula, f.created_at
  FROM usuarios u
  JOIN funcionarios f ON f.usuario_id=u.id
  WHERE u.cpf=current_setting('app.diagnostic_cpf', true)
    AND u.status='ativo' AND f.status='ativo'
), alvo AS (
  SELECT funcionario_id, empresa_id
  FROM vinculos
  ORDER BY (
    matricula=convert_from(
      decode(current_setting('app.diagnostic_registration_b64', true),'base64'),'UTF8'
    )
  ) DESC, created_at DESC
  LIMIT 1
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
  SELECT j.id, j.empresa_id, j.origem
  FROM alvo a CROSS JOIN hoje h
  JOIN jornadas_diarias j ON j.empresa_id=a.empresa_id
    AND j.funcionario_id=a.funcionario_id AND j.data_operacional=h.dia
  LIMIT 1
), estado_jornada AS (
  SELECT
    EXISTS (
      SELECT 1 FROM ultima_jornada j
      JOIN jornada_eventos_esperados e
        ON e.empresa_id=j.empresa_id AND e.jornada_id=j.id
    ) AS possui_eventos,
    EXISTS (
      SELECT 1 FROM ultima_jornada j
      JOIN jornada_eventos_esperados e
        ON e.empresa_id=j.empresa_id AND e.jornada_id=j.id
      WHERE e.marcacao_id IS NULL
    ) AS possui_pendente
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
  SELECT tf.id, tf.resultado,
    (tf.instante <= clock_timestamp()
      AND tf.instante >= clock_timestamp() - interval '120 seconds') AS dentro_janela,
    EXISTS (SELECT 1 FROM marcacoes m WHERE m.tentativa_facial_id=tf.id) AS utilizada,
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
), marcacoes_estado AS (
  SELECT
    EXISTS (
      SELECT 1 FROM alvo a JOIN marcacoes m
        ON m.empresa_id=a.empresa_id AND m.funcionario_id=a.funcionario_id
      WHERE m.instante >= clock_timestamp() - interval '60 seconds'
    ) AS recente,
    EXISTS (
      SELECT 1 FROM alvo a CROSS JOIN hoje h JOIN marcacoes m
        ON m.empresa_id=a.empresa_id AND m.funcionario_id=a.funcionario_id
      WHERE (m.instante AT TIME ZONE 'America/Sao_Paulo')::date=h.dia
    ) AS existe_hoje
), ultimo_terminal AS (
  SELECT empresa_id
  FROM terminais_ponto
  WHERE status='ativo' AND revoked_at IS NULL
  ORDER BY created_at DESC, id DESC LIMIT 1
), terminal_informado AS (
  SELECT empresa_id
  FROM terminais_ponto
  WHERE credencial_hash=current_setting('app.diagnostic_terminal_hash', true)
    AND status='ativo' AND revoked_at IS NULL
  LIMIT 1
)
SELECT
  (EXISTS (SELECT 1 FROM alvo))::int,
  ((SELECT count(*) FROM vinculos)>1)::int,
  (EXISTS (
    SELECT 1 FROM alvo a
    JOIN biometrias b ON b.empresa_id=a.empresa_id AND b.funcionario_id=a.funcionario_id
    JOIN politicas_biometricas p ON p.id=b.politica_biometrica_id AND p.empresa_id=b.empresa_id
    JOIN perfis_tecnicos_biometricos t ON t.id=b.perfil_tecnico_id AND t.empresa_id=b.empresa_id
    WHERE b.status='ativa' AND p.estado='aprovada' AND t.estado='ativo'
      AND p.finalidade='registro_ponto_1a1' AND t.finalidade=p.finalidade
      AND p.vigencia_inicio<=clock_timestamp()
      AND (p.vigencia_fim IS NULL OR p.vigencia_fim>clock_timestamp())
      AND t.vigencia_inicio<=clock_timestamp()
      AND (t.vigencia_fim IS NULL OR t.vigencia_fim>clock_timestamp())
      AND b.modelo=t.modelo AND b.versao_modelo=t.versao_modelo
      AND b.created_at+(p.retencao_dias*interval '1 day')>clock_timestamp()
  ))::int,
  (EXISTS (SELECT 1 FROM atribuicao))::int,
  (EXISTS (SELECT 1 FROM atribuicao at CROSS JOIN hoje h JOIN periodos_turno p ON p.turno_id=at.turno_id AND p.dia_semana=extract(dow FROM h.dia)::int))::int,
  coalesce((SELECT CASE origem WHEN 'sem_jornada' THEN 'sem_jornada' WHEN 'folga' THEN 'folga' ELSE 'configurada' END FROM ultima_jornada),'ausente'),
  coalesce((SELECT resultado FROM ultima_facial),'ausente'),
  coalesce((SELECT motivo FROM ultima_facial),'ausente'),
  coalesce((SELECT dentro_janela::int FROM ultima_facial),0),
  coalesce((SELECT utilizada::int FROM ultima_facial),0),
  coalesce((SELECT possui_eventos::int FROM estado_jornada),0),
  coalesce((SELECT possui_pendente::int FROM estado_jornada),0),
  coalesce((SELECT recente::int FROM marcacoes_estado),0),
  coalesce((SELECT existe_hoje::int FROM marcacoes_estado),0),
  (EXISTS (
    SELECT 1 FROM alvo a JOIN terminais_ponto t ON t.empresa_id=a.empresa_id
    WHERE t.status='ativo' AND t.revoked_at IS NULL
  ))::int,
  (EXISTS (
    SELECT 1 FROM alvo a JOIN ultimo_terminal t ON t.empresa_id=a.empresa_id
  ))::int,
  (EXISTS (SELECT 1 FROM terminal_informado))::int,
  (EXISTS (
    SELECT 1 FROM alvo a JOIN terminal_informado t ON t.empresa_id=a.empresa_id
  ))::int,
  (EXISTS (
    SELECT 1 FROM alvo a JOIN funcionarios f ON f.id=a.funcionario_id
    WHERE f.matricula=convert_from(
      decode(current_setting('app.diagnostic_registration_b64', true),'base64'),'UTF8'
    )
  ))::int,
  (EXISTS (
    SELECT 1 FROM alvo a JOIN funcionarios f ON f.id=a.funcionario_id
    WHERE lower(btrim(f.matricula))=lower(btrim(convert_from(
      decode(current_setting('app.diagnostic_registration_b64', true),'base64'),'UTF8'
    )))
  ))::int,
  coalesce((SELECT resultado FROM ultima_tentativa),'ausente'),
  coalesce((SELECT motivo FROM ultima_tentativa),'ausente');
SQL
export DIAGNOSTIC_SQL

set +e
result="$(docker run --rm --pull=never --entrypoint sh \
  --mount "type=bind,source=$ca_file,target=/run/supabase-ca.crt,readonly" \
  --env PGDATABASE --env PGPASSWORD --env PGSSLMODE --env PGSSLROOTCERT \
  --env ACCOUNT_CPF --env ACCOUNT_REGISTRATION_B64 --env TERMINAL_CREDENTIAL_HASH \
  --env DIAGNOSTIC_SQL \
  postgres:17-alpine -c \
  'exec psql --dbname="$PGDATABASE" --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --command="SET app.diagnostic_cpf TO '\''$ACCOUNT_CPF'\''; SET app.diagnostic_registration_b64 TO '\''$ACCOUNT_REGISTRATION_B64'\''; SET app.diagnostic_terminal_hash TO '\''$TERMINAL_CREDENTIAL_HASH'\''; $DIAGNOSTIC_SQL"' \
  2>"$log_file")"
status=$?
set -e
chmod 600 "$log_file"
if [[ $status -ne 0 ]]; then
  printf 'Diagnostico falhou; nenhum dado foi exibido.\n' >&2
  exit 1
fi
if [[ ! "$result" =~ ^[01]\|[01]\|[01]\|[01]\|[01]\|(ausente|sem_jornada|folga|configurada)\|(ausente|sucesso|falha|bloqueada|expirada)\|(ausente|match|biometria_ausente|liveness_reprovado|nao_corresponde|outro)\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|[01]\|(ausente|confirmada|analise|bloqueada)\|(ausente|evento_confirmado|jornada_nao_configurada|folga_programada|jornada_concluida|sem_evento_esperado|tipo_legado_divergente|marcacao_recente|outro)$ ]]; then
  printf 'Diagnostico retornou formato inesperado; nenhuma linha foi exibida.\n' >&2
  exit 1
fi
IFS='|' read -r conta vinculos_multiplos biometria atribuicao periodo jornada facial_resultado facial_motivo facial_valida facial_utilizada eventos pendente marcacao_recente marcacao_hoje terminal_empresa ultimo_terminal_empresa credencial_valida credencial_mesma_empresa matricula_exata matricula_normalizada jornada_resultado jornada_motivo <<<"$result"
printf 'governanca_diag: biometria_compativel_com_politica_e_perfil_vigentes=%s; jornada_pendente=%s; matricula_exata=%s; credencial_terminal_mesma_empresa=%s.\n' \
  "$biometria" "$pendente" "$matricula_exata" "$credencial_mesma_empresa"
printf 'Diagnostico somente leitura concluido.\n'
