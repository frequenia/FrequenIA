# Fase 30 — Motor de jornada e marcação esperada

## 1. Decisão de domínio

`services/daily_journey.py` é a autoridade única para resolver a jornada e o
próximo evento. Identidade e empresa vêm da sessão/terminal, o instante oficial
vem de `clock_timestamp()`, e timezone, escala, turno e períodos vêm do banco.
O cliente nunca escolhe o tipo confirmado.

A prioridade é: escala/exceção ativa da data, atribuição de turno vigente e
`sem_jornada`. O primeiro início é `entrada`, fins intermediários são
`saida_intervalo`, inícios posteriores são `retorno_intervalo` e o último fim
é `saida`. O padrão se repete para qualquer quantidade válida de períodos.

Uma jornada anterior materializada, incompleta e ainda dentro da janela
operacional tem precedência depois da meia-noite. Horários civis inexistentes
ou ambíguos por DST/mudança de offset são recusados; não há normalização
silenciosa. Adiantamento e atraso são informativos e não produzem cálculo
trabalhista.

## 2. Política de exceções

Consulta de folga ou ausência de jornada apenas informa o estado. Uma tentativa
de marcação sem evento válido, após jornada concluída ou com `tipo` legado
divergente é preservada em `tentativas_jornada`, não cria marcação e cria/reusa
`ordem_invalida` para análise. `falha_facial` permanece independente e ocorre
antes da decisão de jornada. A correção aprovada avança a sequência pela visão
efetiva sem atualizar `marcacoes`.

## 3. Migration 025

`025_daily_journey_engine.sql` cria:

- `escalas_diarias`, com histórico por cancelamento lógico e uma regra ativa
  por empresa/funcionário/data;
- `jornadas_diarias`, snapshot técnico imutável e sem PII/biometria;
- `jornada_eventos_esperados`, com ordem única e vínculo à marcação original;
- `tentativas_jornada`, com idempotência por empresa/chave;
- vínculos tenant-scoped e deduplicação de `ordem_invalida` por ciclo.

A migration é incremental, posterior à `024`, usa timestamps do PostgreSQL e
não altera os eventos nem as transições das Fases 24–29.

## 4. API e autorização

- `GET /api/marcacoes/proxima`: jornada própria; recusa campos de autoridade.
- `GET /api/admin/funcionarios/<id>/escalas`: funcionário próprio, gestor no
  escopo, RH/admin da empresa.
- `POST /api/admin/funcionarios/<id>/escalas`: somente RH/admin da empresa.
- `POST /api/admin/escalas/<id>/cancelar`: somente RH/admin, regra futura e
  ainda não materializada.

Fora da empresa ou escopo retorna o mesmo 404 não enumerável. Criação e
cancelamento de escala, materialização relevante, exceção e vínculo do evento
são auditados com IDs técnicos e metadados sanitizados.

## 5. Registro, concorrência e idempotência

Mobile e quiosque chamam `confirm_expected_event` depois de biometria e
geofence já validadas. O serviço adquire advisory lock por
empresa/funcionário, relê o próximo evento dentro da transação e grava o
instante real com `clock_timestamp()`. A unicidade de `jornada_evento_id` e o
lock impedem duas marcações para o mesmo evento. A mesma chave/operação é
reutilizada; chave associada a outra operação falha com conflito.

O intervalo mínimo homologado permanece. O fluxo administrativo/importado não
usa esse endpoint e continua separado.

## 6. Interfaces

Flutter e quiosque não exibem seletor nem enviam `tipo`. Ambos apresentam o
tipo decidido pelo backend; o Flutter consulta a próxima marcação e mostra
próxima, concluída, folga, sem jornada e análise. A gestão reutiliza `/jornadas`
para incluir escala/folga por data e consultar histórico; gestor permanece
somente leitura.

## 7. Observabilidade

`services/journey_observability.py` emite eventos JSON com enumerações de baixa
cardinalidade: origem/estado, tipo de evento, faixa temporal, resultado e
motivo técnico. Pessoa, empresa, snapshot, marcação, ocorrência, PII,
biometria e localização não são dimensões nem payload de log.

## 8. CI e reprodução local

`.github/workflows/phase26-quality.yml` mantém PostgreSQL/pgvector e regressões
das Fases 25–29, acrescentando a suíte explícita da Fase 30. A descoberta
padrão mantém integrações em `skip` explícito; a etapa dedicada define
`PHASE30_TEST_DATABASE_URL`, portanto não as ignora silenciosamente. Flutter
continua em job separado. Nenhum secret real é necessário.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
$env:PHASE30_TEST_DATABASE_URL = `
  "postgresql://postgres:DESCARTAVEL@127.0.0.1:55435/frequenia_phase25_test"
python -m unittest discover -s tests -p "test_phase30_postgres_integration.py" -v
Set-Location mobile
flutter analyze --no-pub
flutter test --no-pub
```

## 9. Matriz individual dos 70 critérios

| # | Evidência | Resultado |
|---:|---|---|
| 1 | `build_planned_events`; unitário de um período | passa |
| 2 | mapeamento do fim intermediário; unitário multiperíodo | passa |
| 3 | mapeamento de início posterior; unitário multiperíodo | passa |
| 4 | mapeamento do último fim; unitário de um período | passa |
| 5 | PG `test_01` materializa quatro períodos/oito eventos | passa |
| 6 | constraints da `004` + teste unitário de contrato | passa |
| 7 | `build_planned_events` recusa sequência não crescente | passa |
| 8 | `fim_dia_offset` em `local_wall_time`; unitário noturno | passa |
| 9 | data operacional permanece a data de início | passa |
| 10 | PG `test_09` prioriza snapshot anterior aberto | passa |
| 11 | resolução só abre a data local quando não há anterior aplicável | passa |
| 12 | `ZoneInfo` do turno e teste com offsets distintos | passa |
| 13 | gaps/folds DST falham fechado em testes unitários | passa |
| 14 | PG `test_07` retorna `sem_jornada` sem inventar tipo | passa |
| 15 | PG `test_01` usa atribuição vigente | passa |
| 16 | PG `test_10` prioriza troca por data | passa |
| 17 | `escalas_diarias` preserva origem/justificativa/histórico | passa |
| 18 | PG `test_02` materializa folga sem eventos | passa |
| 19 | PG `test_10` cancela logicamente e restaura turno inferior | passa |
| 20 | índice parcial `escalas_diarias_ativa_unique` | passa |
| 21 | FK composta empresa/funcionário + 404 nas rotas | passa |
| 22 | mutação exige RH/admin no backend | passa |
| 23 | gestor usa `employee_visibility_query` | passa |
| 24 | RH/admin sempre filtram empresa da sessão | passa |
| 25 | trigger torna snapshot imutável; PG `test_03` | passa |
| 26 | duas conexões, `ON CONFLICT`, um snapshot; PG `test_03` | passa |
| 27 | unicidade `(jornada_id, ordem)` e oito eventos ordenados | passa |
| 28 | PG `test_01` inspeciona JSON sem PII/biometria | passa |
| 29 | endpoint deriva IDs da autenticação | passa |
| 30 | endpoint recusa `empresa_id`, `funcionario_id`, timezone e tipo | passa |
| 31 | testes de contrato Flutter/quiosque sem `tipo` | passa |
| 32 | PG `test_04` bloqueia tipo legado divergente | passa |
| 33 | resposta usa `marking.tipo` decidido pelo serviço | passa |
| 34 | INSERT usa `clock_timestamp()`; teste de contrato | passa |
| 35 | diferença negativa só informa `timing_bucket` | passa |
| 36 | diferença positiva não muda o evento | passa |
| 37 | configuração negativa/zero é recusada no startup | passa |
| 38 | criação administrativa permanece indisponível/separada | passa |
| 39 | PG `test_04` confirma primeiro e avança | passa |
| 40 | visão sequencial conclui após todos os eventos | coberto pelo motor/constraints |
| 41 | concorrência PG `test_06` preserva intervalo mínimo | passa |
| 42 | PG `test_05` reutiliza a mesma chave/operação | passa |
| 43 | PG `test_05` recusa chave com operação diferente | passa |
| 44 | PG `test_06`, duas conexões, uma marcação | passa |
| 45 | `concluida` entra no fluxo de tentativa/análise | passa |
| 46 | folga nunca cria marcação confirmada | passa |
| 47 | PG `test_07` sem jornada não cria marcação | passa |
| 48 | PG `test_07` preserva `tentativas_jornada` | passa |
| 49 | PG `test_04` cria `ordem_invalida` quando aplicável | passa |
| 50 | índice parcial de ciclo e `ON CONFLICT DO NOTHING` | passa |
| 51 | suíte facial completa + teste de contrato separado | passa |
| 52 | exceção só grava tentativa/ocorrência; original permanece | passa |
| 53 | PG `test_08` inclui correção aprovada na sequência | passa |
| 54 | PG `test_08` rejeitada não avança | passa |
| 55 | regressões de visão efetiva/exportações das Fases 24–26 | passa |
| 56 | Flutter mostra próxima marcação sem seletor | passa |
| 57 | `_journeyMessage` cobre concluída/folga/sem jornada/análise | passa |
| 58 | template/JS do quiosque não oferecem `tipo` | passa |
| 59 | `/jornadas` recebeu escala/folga na navegação existente | passa |
| 60 | auditoria e observabilidade possuem somente campos técnicos | passa |
| 61 | dimensões são enumerações de baixa cardinalidade | passa |
| 62 | GET pessoal não escreve auditoria | passa |
| 63 | PG `test_00` aplica instalação limpa `001`–`025` | passa |
| 64 | PG `test_00` aplica `001`–`024 → 025` e preserva marcação | passa |
| 65 | constraints/FKs/índices tenant/data exercitados em PG | passa |
| 66 | regressões existentes de jornadas/facial/geofence | passa |
| 67 | integrações dedicadas das Fases 25–29 | passa |
| 68 | descoberta backend: 320 testes, 84 skips explícitos, 0 falhas | passa |
| 69 | `flutter analyze --no-pub`: No issues found | passa |
| 70 | `flutter test --no-pub`: 48 testes, 0 falhas | passa |

## 10. Resultados executados

- descoberta backend: **320 executados; 236 sucessos, 84 skips explícitos,
  0 falhas**;
- Fase 25 PostgreSQL: **31/31**;
- Fase 26 PostgreSQL: **17/17**;
- Fase 27 PostgreSQL + Moto S3 + ClamAV/EICAR: **8/8**;
- Fase 28 PostgreSQL + fila/SQS compatível: **9/9**;
- Fase 29 PostgreSQL + export/restore descartável: **7/7**;
- Fase 30 PostgreSQL: **12/12**;
- Flutter analyze: **0 issues**;
- Flutter test: **48/48**.
- `cfn-lint infra/aws/attachments.template.yaml`: **0 achados**;
- `cfn-guard` e `gitleaks` não estavam instalados localmente. Os contratos
  equivalentes da infraestrutura/CI passaram e a busca local no diff não
  encontrou padrões de chave privada, access key ou segredo atribuído. O
  secret scanning remoto permanece pendente junto com o run de CI.

O PostgreSQL/pgvector, Moto, ClamAV e arquivos usados eram descartáveis. O run
remoto do GitHub Actions permanece pendente porque não houve commit/push/PR.
Os três contêineres e o shim temporário de `pg_dump`/`pg_restore` foram
removidos ao final.

## 11. Limitações e Fase 31

- tolerâncias permanecem informativas; não há cálculo jurídico, banco de horas
  ou folha;
- feriados, recorrência complexa e troca solicitada pelo funcionário continuam
  fora de escopo;
- timezone/DST inválido exige ajuste administrativo, sem escolha automática;
- homologação com volume e fusos reais deve usar dados sintéticos aprovados;
- a Fase 31 pode tratar planejamento recorrente/feriados aprovados, política de
  fechamento operacional e painéis agregados, sem reabrir snapshots históricos.

Não houve commit, push, PR, deploy, provisionamento ou acesso à produção.
