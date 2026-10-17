# Fase 29 — Continuidade, caos e backup verificável

## 1. Política e decisão arquitetural

- **Backup operacional:** cópia governada, criptografada, monitorada e aprovada
  para recuperação real. Não foi implantado nesta fase.
- **Snapshot/exportação de teste:** cópia sintética e descartável para validar
  ferramentas; não constitui backup operacional.
- **Restauração:** materialização de um conjunto previamente verificado em
  destino isolado e vazio.
- **Exercício de continuidade:** ensaio periódico de backup, restore, redrive e
  validação, com evidências sanitizadas.
- **Disaster recovery:** capacidade organizacional de recuperar um desastre,
  incluindo pessoas, regiões, dependências e RPO/RTO; permanece fora do escopo.
- **Alta disponibilidade:** continuidade automática durante falhas, distinta de
  backup e DR; não foi alterada.
- **Retenção:** decisão do PostgreSQL sobre por quanto tempo preservar dados.
- **Versionamento:** versões não correntes de objetos; permanece desabilitado
  até haver política de custo, expiração e recuperação aprovada.

Os defaults locais são apenas limites de teste: RPO 1 hora, RTO 2 horas,
frequência 24 horas, retenção 30 dias, janela 60 minutos e conjunto de até
1 GiB. Todos os valores de produção permanecem em **aprovação corporativa pendente**.
A aplicação somente reconhece aprovação quando ambiente, flag e
referência formal são coerentes.

## 2. Classificação dos dados

PostgreSQL/migrations, objetos privados, manifestos e configuração não secreta
podem compor um conjunto autorizado. Outbox e estados reprocessáveis são
preservados para retomada. Evidências guardam somente IDs opacos, contagens,
bytes, duração e hashes. `.env`, credenciais, tokens, caches, logs brutos,
temporários e URLs nunca são copiados. Biometria possui política jurídica
separada; nenhum dado biométrico real participa dos exercícios.

## 3. Manifesto verificável

O schema v1 contém UUID do conjunto, ambiente lógico, timestamp UTC,
componentes, migrations, contagens, bytes, checksums SHA-256, criptografia
esperada, verificação e RPO/RTO usados. O envelope possui checksum canônico do
manifesto. Versão desconhecida, envelope adulterado, campo inesperado, arquivo
ausente, tamanho/hash divergente ou conjunto parcial falham fechado antes do
restore. O manifesto nunca contém conteúdo, PII, segredo, URL ou chave S3.

Diretórios precisam ficar fora do repositório e de `static/`; arquivos e pasta
recebem permissões restritivas. A criptografia declarada no exercício local usa
chave efêmera apenas em teste; uma solução corporativa de chaves permanece
pendente e não há chave no repositório.

## 4. Migration 024

`024_continuity_backup_chaos.sql` cria `execucoes_continuidade`, histórico
append-only e `anexo_purge_tag_jobs`. Armazena controle sanitizado, estados,
timestamps do PostgreSQL, contagens, bytes, duração, RPO/RTO observados,
integridade e erro controlado. Não armazena dump ou objeto. Também adiciona
hold (`preservacao_ate`) e autorização persistida (`purge_autorizado_at`).

Constraints, FKs, índices tenant-scoped e unicidade por anexo tornam execução
concorrente e retomada determinísticas. Instalação limpa `001`–`024` e upgrade
`001`–`023 → 024` são parte da integração opt-in.

## 5. Backup e restore descartáveis

As ferramentas `prepare_continuity_backup.py`, `verify_continuity_backup.py` e
`restore_continuity_backup.py` são dry-run por padrão. Execução exige flag,
recusa produção, origem=destino, conjunto acima do limite, diretório público ou
destino não vazio sem autorização específica. Artefatos recebem nomes técnicos
gerados; entradas nunca viram fragmentos de shell. Um journal permite retomar
restore interrompido sem marcá-lo prematuramente como concluído.

O exercício PostgreSQL é de snapshot/exportação sintética e restauração em
base descartável. Uma política operacional de `pg_dump`/PITR, cofre de chaves,
retenção e agendamento depende de aprovação corporativa.

## 6. Redrive controlado

O redrive apenas planeja por padrão. Execução exige autorização, motivo e lote
limitado. Payload, versão, UUIDs, tenant, anexo e job são revalidados sob lock.
Job terminal não reabre. A origem somente é confirmada depois que publicação e
persistência terminam; falha preserva a mensagem. SQS continua at-least-once:
idempotência de domínio, não a fila, impede efeitos duplicados.

## 7. Caos e capacidade

O harness exige simultaneamente `APP_ENV=test` e token fixo da fixture, não
aceita payload HTTP e recusa produção. Pontos determinísticos cobrem banco,
storage, checksum, SQS, worker, scanner, assinatura, manifesto e restore. O
relógio controlado elimina dependência do tempo real.

A carga sintética aceita no máximo 10.000 mensagens e 32 workers, sem endpoint
externo ou PII. Mede throughput, p50/p95/p99, backlog máximo/drenado, recuperação,
retry, DLQ e erro. CPU/memória são opcionais e não requerem privilégio. Todo
resultado é rotulado `local_synthetic_not_production_slo`.

## 8. Elegibilidade de purga

A autorização seleciona somente registro existente, não ativo, retenção
vencida, sem hold e com segurança terminal. Ela persiste autorização e job e
faz commit antes de qualquer chamada S3. O dispatcher relê e bloqueia o job,
valida estado, tamanho e checksum, então aplica exclusivamente
`frequenia-purge-eligible=true`. Dry-run não altera nada; falha de storage fica
reprocessável e nunca conclui purga nem remove objeto.

## 9. Observabilidade e objetivos

EMF preserva dimensões de baixa cardinalidade. Métricas incluem idade do último
backup verificável, integridade, duração p95/p99, RPO/RTO observado, redrive,
caos de teste, drenagem e tagging. Heartbeat trata ausência como falha; erros
esparsos tratam ausência como não violação. Dashboard e parâmetros avisam que
thresholds exigem calibração em homologação.

## 10. Infraestrutura, IAM e compliance

CloudFormation mantém bucket privado, TLS, SSE, ownership enforced,
`DeletionPolicy`/`UpdateReplacePolicy: Retain`, lifecycle apenas para multipart
e objetos já marcados. Filas permanecem privadas, criptografadas, retidas e
com redrive. Não há service principal; se surgir, `aws:SourceAccount` e
`aws:SourceArn` serão obrigatórios.

IAM separa backup read-only, restore, redrive, tagging e evidências por
ARN/prefixo. `attachments.guard` cobre público, HTTP, criptografia, retenção e
fila. KMS CMK e versionamento continuam condicionados a decisão formal.
Nenhum recurso foi aplicado.

## 11. Runbooks

Os dez procedimentos estão em `docs/runbooks/FASE_29_CONTINUIDADE.md` e proíbem
bypass de scanner, autorização, retenção, auditoria ou uso de dados reais.

## 12. Matriz dos 70 critérios

| # | Evidência executável | Resultado local |
|---:|---|---|
| 1 | seção 1 e `test_policy_documentation_distinguishes_continuity_terms` | passou |
| 2 | `test_policy_is_validated_and_production_values_remain_pending` | passou |
| 3 | validações de `continuity_policy.py` | passou |
| 4 | `test_manifest_is_versioned_opaque_sanitized_and_verified` | passou |
| 5 | inspeção sanitizada do manifesto no mesmo teste | passou |
| 6 | checksum no build/load do manifesto | passou |
| 7 | `test_manifest_tampering_unknown_version_and_partial_set_fail_closed` | passou |
| 8 | versão desconhecida no mesmo teste | passou |
| 9 | artefato ausente no mesmo teste | passou |
| 10 | `test_00_migration_024_upgrade_and_clean_install` | passou |
| 11 | upgrade 001–023 → 024 no mesmo teste | passou |
| 12 | `test_09_operational_history_constraints_and_append_only_evidence` | passou |
| 13 | `test_backup_and_restore_are_dry_run_explicit_isolated_and_resumable` | passou |
| 14 | `--execute` e dry-run nos serviços/CLIs | passou |
| 15 | `_safe_environment`/`parse_disposable_database` | passou |
| 16 | recusa de origem=destino | passou |
| 17 | recusa de destino não vazio | passou |
| 18 | `test_postgres_commands_are_argument_safe_and_credentials_are_environment_only` | passou |
| 19 | `test_14_real_pg_dump_manifest_and_isolated_restore` | passou |
| 20 | restauração de artefatos no bundle verificado | passou |
| 21 | checksums no destino e dump não vazio | passou |
| 22 | regressão Fase 28 `test_07_disposable_database_snapshot_restore_preserves_security_state` | passou |
| 23 | mesma regressão, leitura somente de ativo+limpo | passou |
| 24 | mesma regressão, outbox pendente restaurada | passou |
| 25 | journal e retomada controlada | passou |
| 26 | temporários em `TemporaryDirectory`/`finally` | passou |
| 27 | plano no `test_13_redrive_plan_validation_terminal_and_success` | passou |
| 28 | autorização, motivo e lote no mesmo teste | passou |
| 29 | payload inválido em `test_phase28_async_contracts` | passou |
| 30 | validação empresa/job/anexo sob lock | passou |
| 31 | terminal rejeitado no teste 13 | passou |
| 32 | idempotência das regressões de worker Fase 28 | passou |
| 33 | limite de falhas do redrive | passou |
| 34 | delete somente depois do commit | passou |
| 35 | auditoria sanitizada `anexo.redrive_controlado` | passou |
| 36 | locks/idempotência PostgreSQL das Fases 28/29 | passou |
| 37 | rollback/outbox atômico Fase 28 | passou |
| 38 | publicação pós-commit reprocessável Fase 28 | passou |
| 39 | storage indisponível fail-closed Fase 27 | passou |
| 40 | checksum divergente Fase 27 | passou |
| 41 | dispatcher preserva outbox Fase 28 | passou |
| 42 | duplicação/fora de ordem Fase 28 | passou |
| 43 | ack pós-commit Fase 28 | passou |
| 44 | timeout/erro/desconhecido do scanner Fases 27/28 | passou |
| 45 | assinatura vencida falha readiness | passou |
| 46 | manifesto truncado/adulterado | passou |
| 47 | restore interrompido não cria `restore.complete` | passou |
| 48 | `ChaosHarness` exige ambiente e token de teste | passou |
| 49 | `ControlledClock` determinístico | passou |
| 50 | gates de download e eventos recuperáveis das regressões | passou |
| 51 | carga limitada a 10.000, sem I/O externo | passou |
| 52 | throughput e p50/p95/p99 | passou |
| 53 | backlog pico/drenado | passou |
| 54 | `recovery_seconds` medido | passou |
| 55 | contratos EMF de baixa cardinalidade | passou |
| 56 | contratos de M-de-N/missing-data | passou |
| 57 | alarme de heartbeat com ausência | passou |
| 58 | erro esparso com `notBreaching` | passou |
| 59 | rótulo `local_synthetic_not_production_slo` | passou |
| 60 | dry-run de tagging no teste 10 | passou |
| 61 | ativo bloqueado no teste 10 | passou |
| 62 | retenção/preservação/segurança revalidadas no dispatcher | passou |
| 63 | commit de autorização antes do storage no teste 11 | passou |
| 64 | falha reprocessável no teste 12 | passou |
| 65 | `infra/aws/attachments.guard` e contrato Python equivalente | passou; binário ausente |
| 66 | `cfn-lint` e parsing YAML | passou |
| 67 | políticas IAM separadas e prefix-scoped | passou |
| 68 | suítes PostgreSQL 25–29 | passou: 72 testes |
| 69 | `flutter analyze` | passou, sem issues |
| 70 | `flutter test --no-pub` | passou, 48 testes |

## 13. Aprovações e limitações

- RPO/RTO, frequência, retenção, agendamento e responsáveis de produção estão
  pendentes de aprovação corporativa.
- Backup operacional, PITR, DR multi-região, KMS CMK, versionamento e política
  jurídica biométrica não foram definidos nem simulados como concluídos.
- Emuladores comprovam contratos locais, não comportamento integral da AWS.
- `cfn-guard` será executado somente se já estiver disponível; caso contrário,
  os testes de contrato permanecem a evidência reproduzível.
- Run remoto da CI depende de commit/push, que não estão autorizados.

## 14. Recomendações para a Fase 30

Formalizar proprietários, RPO/RTO e política jurídica; escolher backup/PITR e
cofre de chaves; homologar restore e redrive em conta isolada; calibrar carga e
alarmes; decidir versionamento/CMK; agendar exercícios com aprovação e retenção
de evidências.

## 15. Registro de execução

Executado em 15/10/2026, exclusivamente em Windows/WSL e containers locais:

- descoberta backend: 298 testes, 226 sucessos, 72 skips opt-in, zero falhas;
- contratos Fase 29: 9/9;
- PostgreSQL Fase 25: 31/31;
- PostgreSQL Fase 26: 17/17;
- PostgreSQL/S3 compatível/ClamAV Fase 27: 8/8, incluindo EICAR;
- PostgreSQL/SQS compatível Fase 28: 9/9;
- PostgreSQL Fase 29: 7/7, incluindo migration limpa/upgrade, concorrência,
  redrive e `pg_dump`/`pg_restore` 16 reais em banco isolado;
- total das integrações PostgreSQL Fases 25–29: 72/72;
- `flutter analyze --no-pub -v`: sem issues, análise em 59,0 s;
- `flutter test --no-pub`: 48/48;
- `cfn-lint`: zero diagnósticos; YAML do workflow válido; contratos CI 5/5;
- carga sintética limitada (200 mensagens, 4 workers): 261,44 msg/s,
  processamento p50 16,00 ms, p95 16,00 ms, p99 16,00 ms, backlog 200→0 e
  recuperação 0,765 s. É evidência local, não SLO de produção;
- RPO observado: 0 s no cenário sintético de snapshot imediato após commit;
  RTO superior observado: 13,827 s para a suíte Fase 29 completa que incluiu
  exportação, manifesto, restore e validação. Não é compromisso corporativo;
- IAM Policy Autopilot 0.3.0 foi usado como baseline local; permissões amplas
  propostas (KMS, Object Lambda, ACL, versionamento/legal hold) foram rejeitadas;
- `cfn-guard` não estava instalado e não foi instalado, conforme restrição. As
  regras foram versionadas e os contratos equivalentes passaram;
- run remoto da CI não ocorreu, pois commit/push não foram autorizados.

O primeiro ensaio foi interrompido por falta de espaço no disco, que colocou o
WSL em estado de I/O/read-only. Foram removidos somente artefatos ignorados e
regeneráveis de `mobile/build`; depois disso todas as suítes acima passaram.
Os containers, rede, dumps e bancos temporários foram removidos ao final.

Nenhum teste local constitui garantia de produção. Não houve commit, push, PR,
deploy, provisionamento cloud, consulta a conta AWS nem acesso à produção.
