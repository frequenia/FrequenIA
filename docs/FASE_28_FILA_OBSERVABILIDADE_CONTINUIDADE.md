# Fase 28 — Fila, observabilidade e continuidade

## 1. Decisão arquitetural da fila

A varredura deixa o request HTTP e passa a uma fila SQS Standard com entrega
pelo menos uma vez. PostgreSQL continua sendo a autoridade para segurança,
autorização, idempotência e retenção. O upload persiste anexo em quarentena e
job de outbox na mesma transação; o dispatcher somente publica linhas já
commitadas. O processo web não inicia consumidor em background.

Produção exige `ATTACHMENT_SCAN_MODE=async`, fila SQS e storage S3. A fila em
memória e o scanner falso são exclusivos de testes. Nenhum cliente escolhe
fila, bucket, endpoint, chave ou resultado de scan.

## 2. Entrega, retry e DLQ

`infra/aws/attachments.template.yaml` declara fila Standard privada, DLQ
separada, SSE-SQS, long polling de 20 segundos, visibility timeout
parametrizado e maior que o timeout do scanner, redrive conservador e retenção
das filas no ciclo de vida do stack. O payload estrito contém somente versão e
UUIDs de job, anexo e empresa; não contém PII, nome, MIME, hash, bucket, chave
ou caminho.

O worker confirma a mensagem apenas depois de persistir um estado terminal.
Erros transitórios e falhas de persistência não confirmam; duplicatas e
mensagens fora de ordem não reabrem estado terminal. Mensagens inválidas nunca
liberam o anexo e seguem o redrive da fila até a DLQ. A extensão de visibility
é limitada e o encerramento interrompe polling sem apagar lote não concluído.

## 3. Migration e outbox

`023_attachment_scan_outbox.sql` cria `anexo_varredura_jobs` com tenant
composto, versão de schema, estados, tentativas de publicação/processamento,
próxima tentativa, timestamps do banco, erro sanitizado e identificador opaco
da mensagem. A unicidade por anexo impede jobs equivalentes. Dispatcher e
workers usam locks transacionais e `SKIP LOCKED` onde há seleção concorrente.

Estados: `pendente_publicacao`, `publicado`, `processando`, `concluido`,
`falha_reprocessavel` e `falha_terminal`. Retry HTTP reaproveita o job; falha
de publicação mantém estado reprocessável e backoff limitado.

## 4. Dispatcher e worker

`services/attachment_outbox.py` e
`tools/dispatch_attachment_scan_jobs.py` implementam execução única ou
contínua. `services/attachment_worker.py` e
`tools/run_attachment_scan_worker.py` implementam consumidor separado, lote
pequeno, validação estrita, lease, idempotência, extensão de visibility e
shutdown controlado. Ambos reutilizam clientes SDK com cadeia padrão de
credenciais, timeout e retry limitados.

A varredura permanece fail-closed: apenas `ativo + limpo` baixa. Quarentena,
infectado, erro, timeout, estado desconhecido ou dependência indisponível não
entregam bytes.

## 5. Métricas, alarmes e dashboard

Eventos JSON admitem apenas IDs técnicos opacos e campos sanitizados. EMF usa
somente dimensões de baixa cardinalidade (`environment`, `process`, `result`),
nunca usuário, empresa, anexo, job, request ou sessão. São emitidas contagens,
idade do job, backlog, mensagens visíveis/em voo/DLQ, duração, falhas,
heartbeat, quarentena e divergências.

CloudFormation declara alarmes para DLQ, idade do backlog, quarentena atrasada,
scanner, assinaturas, taxa de falhas e heartbeat. Alarmes aplicáveis usam M-de-N
e `TreatMissingData` explícito; duração usa p99. Thresholds operacionais e
destino SNS são parametrizáveis, sem criar assinatura. O dashboard contém
backlog e duração p99.

## 6. Operação das assinaturas ClamAV

A interface consulta `VERSION`, extrai versão e data e calcula idade. Resposta
ausente/inválida, timeout ou idade maior que
`CLAMAV_SIGNATURE_MAX_AGE_HOURS` torna a readiness do worker indisponível.
`freshclam` é responsabilidade operacional separada; a aplicação não executa
atualização solicitada por usuário. Logs contêm apenas versão, idade e resultado
sanitizado.

## 7. Lifecycle e retenção

PostgreSQL permanece autoridade. O bucket aborta multipart incompleto após
sete dias. A única expiração declarada exige tag
`frequenia-purge-eligible=true`, aplicada somente após decisão persistida, e
margem adicional configurável. Anexo ativo nunca recebe essa elegibilidade; a
purga auditada continua sendo o mecanismo primário.

O versionamento permanece desabilitado por decisão consciente: habilitá-lo
sem uma política completa poderia deixar versões antigas fora da purga. Risco
residual é reduzido por chaves imutáveis opacas, `DeletionPolicy: Retain`,
checksums, reconciliação e exercício de continuidade. Backup/versionamento
corporativo requer decisão futura. SSE-S3/SSE-SQS são usados; CMK fica
condicionada a exigência formal de compliance e custo.

## 8. Reconciliação

`reconcile_correction_attachments.py` é read-only por padrão, tenant-scoped e
paginado. Detecta metadado sem objeto, objeto sem metadado, quarentena sem job,
job concluído com anexo não terminal, limpo em prefixo incorreto, objeto
elegível à purga ainda presente e divergência de tamanho/checksum. A saída
mostra contagens e IDs opacos, nunca chave completa ou PII.

O único reparo automatizado suportado é recriar/reencaminhar job ausente; exige
simultaneamente operação explícita, `--execute` e empresa validada. Objeto
desconhecido nunca é apagado automaticamente.

## 9. Continuidade e restauração

A integração da Fase 28 cria banco e objetos sintéticos, copia o storage para
diretório isolado, restaura o banco para uma segunda base descartável, executa
verificações de integridade e confirma que limpos permanecem íntegros e que
quarentena permanece bloqueada e retomável. Base e diretórios temporários são
removidos no `finally`. Não foram usados backup real nem recurso externo.

## 10. Runbooks

`docs/runbooks/FASE_28_OPERACAO_ANEXOS.md` cobre backlog, DLQ/redrive, scanner
indisponível, assinaturas antigas, storage indisponível, malware, divergência,
continuidade/restauração e rollback seguro. Cada procedimento contém sintomas,
métricas, diagnóstico, contenção, recuperação, validação e evidência. Ações
destrutivas são explicitamente manuais e condicionadas a autorização.

## 11. IAM e infraestrutura declarativa

As políticas separam runtime S3, publisher SQS, worker SQS e operador de
redrive. Recursos são limitados aos ARNs/prefixos declarados; não há wildcard
de recurso nos allows. Não existe service principal nesta fila, portanto não
há policy que necessite `aws:SourceArn`/`aws:SourceAccount`; se um produtor de
serviço for adicionado, proteção contra confused deputy torna-se obrigatória.

IAM Policy Autopilot foi usado somente como baseline local sobre o código
Python. Permissões genéricas sugeridas (KMS, Object Lambda, ACL, versionamento e
outros recursos não usados) foram rejeitadas. O template passou no `cfn-lint`;
`cfn-guard` não estava instalado. Nenhum template, policy ou change set foi
enviado/aplicado e nenhum recurso AWS foi consultado ou criado.

## 12. Testes executados

Execução local final em 15/10/2026:

- descoberta backend: 282 executados, 217 aprovados e 65 skips explícitos;
- Fase 25/PostgreSQL: 31 aprovados, sem skips/falhas;
- Fase 26/PostgreSQL: 17 aprovados, sem skips/falhas;
- Fase 27/PostgreSQL + Moto S3 + ClamAV: 8 aprovados, sem skips/falhas;
- Fase 28/PostgreSQL + fila em memória + Moto SQS + restauração: 9 aprovados,
  sem skips/falhas;
- `flutter analyze`: sem issues;
- `flutter test`: 48 aprovados;
- `cfn-lint`: nenhum diagnóstico; `cfn-guard` indisponível.

O ClamAV descartável respondeu a `PING`/`VERSION`; a leitura final indicou
assinaturas com 13,29 horas, abaixo do limite local de 48 horas. Ao terminar,
foram removidos a base, a cópia de storage, o pacote Moto temporário e os três
contêineres descartáveis da rodada.

A matriz de 60 cenários está coberta por
`test_phase28_async_contracts.py`, `test_phase28_postgres_integration.py`,
regressões das Fases 25–27, testes de CI/configuração, template e runbooks.
Outbox/publicação 1–10; worker/SQS 11–24; métricas/alarmes/ClamAV 25–35;
lifecycle/reconciliação/continuidade 36–50; segurança/regressão 51–60. A suíte
opt-in não é ignorada na CI. O run remoto permanece pendente porque commit e
push não foram autorizados.

## 13. Limitações

- Nenhuma fila, bucket, alarme, policy ou assinatura foi provisionada.
- O emulador Moto valida contrato SQS/S3, não toda a semântica distribuída AWS.
- Redrive em produção, atualização freshclam e resposta a alarmes continuam
  responsabilidades operacionais.
- Versionamento/backup corporativo, testes periódicos de restore em ambiente
  homologado e eventual CMK dependem de decisão formal.
- Lifecycle é apenas rede de segurança; aplicação de tag purge-eligible deve
  permanecer posterior ao estado persistido e auditado.

## 14. Recomendações para a Fase 29

- exercício periódico autorizado de restore e redrive em homologação isolada;
- política corporativa de backup, versionamento e objetivos RPO/RTO;
- decidir CMK e rotação somente se compliance exigir;
- automação operacional controlada da tag de purge-eligible após commit;
- testes de caos de indisponibilidade prolongada e capacidade do worker;
- revisão de dashboards/thresholds com dados reais sanitizados do piloto.
