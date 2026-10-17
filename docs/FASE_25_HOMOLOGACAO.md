# Fase 25 — Homologação do workflow Gestor → RH

## Evidências por critério

Todos os cenários abaixo são executados em PostgreSQL real por
`tests/test_phase25_postgres_integration.py`.

| # | Cenário | Evidência principal |
|---:|---|---|
| 1 | nasce `pendente_gestor` | `test_01_request_starts_pending_manager` |
| 2 | gestor no escopo aprova | `test_02_scoped_manager_approves` |
| 3 | gestor rejeita com justificativa | `test_03_scoped_manager_rejects_with_justification` |
| 4 | gestor encaminha ao RH | `test_04_manager_forwards_to_hr_with_observation` |
| 5 | RH aprova somente encaminhada | `test_05_hr_approves_only_forwarded` |
| 6 | RH rejeita somente encaminhada | `test_06_hr_rejects_only_forwarded` |
| 7 | política do administrador | `test_07_admin_follows_forwarded_policy_in_own_company` |
| 8 | estado final não transiciona | `test_08_final_state_never_transitions` |
| 9 | transição inválida coerente | `test_09_invalid_transition_is_coherent` |
| 10 | gestor fora do escopo recebe 404 | `test_10_out_of_scope_manager_gets_non_enumerable_404` |
| 11 | RH/admin cross-tenant recebem 404 | `test_11_foreign_hr_and_admin_cannot_read_or_change` |
| 12 | funcionário não decide | `test_12_employee_cannot_decide` |
| 13 | funcionário lê somente a própria | `test_13_employee_reads_only_own_request` |
| 14 | cancelamento somente pendente | `test_14_employee_cancels_only_pending` |
| 15 | marcação byte a byte imutável | `test_15_original_marking_is_byte_for_byte_unchanged` |
| 16 | visão aplica horário | `test_16_effective_view_reflects_approved_time` |
| 17 | visão aplica tipo | `test_17_effective_view_reflects_approved_type` |
| 18 | visão aplica inclusão | `test_18_effective_view_reflects_approved_inclusion` |
| 19 | exportações usam visão efetiva | `test_19_exports_use_same_effective_view` |
| 20 | rejeitada/cancelada não afetam visão | `test_20_rejected_and_cancelled_do_not_change_effective_view` |
| 21 | um evento por transição | `test_21_each_transition_generates_exactly_one_audit_event` |
| 22 | auditoria contém contexto completo | `test_22_audit_records_actor_role_tenant_employee_states_and_reason` |
| 23 | timestamps vêm do PostgreSQL | `test_23_official_timestamps_are_generated_by_postgresql` |
| 24 | notificação interna aplicável | `test_24_internal_notification_is_created_when_applicable` |
| 25 | duas decisões, uma vencedora | `test_25_two_simultaneous_decisions_have_one_winner` |
| 26 | aprovação/rejeição não sobrescrevem | `test_26_concurrent_approval_and_rejection_do_not_overwrite` |
| 27 | aprovações não duplicam aplicação | `test_27_two_concurrent_approvals_do_not_duplicate_application` |
| 28 | conflito HTTP 409 | `test_28_http_conflict_is_409` |
| 29 | payload manual não ganha autoridade | `test_29_manual_calls_cannot_override_server_authority` |
| 30 | `falha_facial` sem regressão | `test_30_facial_failure_workflow_remains_independent` |

O teste `test_00_migrations_clean_upgrade_constraints_indexes_and_foreign_keys`
é adicional: valida instalação limpa, upgrade de estados legados, constraints,
FKs e índices.

## Correção descoberta

A constraint anônima criada na migration `008` exigia `decisao IS NOT NULL`
também para aprovação. Isso contrariava o contrato atual, no qual a observação
de aprovação é opcional, e produzia HTTP 500 no PostgreSQL real. A migration
`018` agora substitui a constraint legada por
`correcoes_decisao_estado_check`: responsável e timestamp continuam
obrigatórios nos estados decididos e a justificativa permanece obrigatória e
não vazia para rejeição.

## Resultado registrado em 7 de outubro de 2026

- integração PostgreSQL: 31 testes aprovados, 0 falhas, 0 skips;
- concorrência: duas conexões psycopg2 independentes sincronizadas por barreira;
- `flutter analyze`: sem issues;
- `flutter test`: 48 testes aprovados, 0 falhas;
- suíte backend de descoberta padrão: 205 testes executados, 174 aprovados,
  31 skips explícitos da integração PostgreSQL, 0 falhas e 0 erros.

Nenhuma migration foi aplicada em produção e nenhuma credencial real foi usada.

## Itens recomendados para a Fase 26

1. projetar anexos opcionais com política de retenção, autorização e varredura;
2. automatizar a suíte PostgreSQL efêmera no CI com pgvector;
3. executar homologação externa autorizada com dados sintéticos e observabilidade;
4. definir requisitos de push e preferências de notificação antes de implementar;
5. planejar relatórios/XLSX/espelho de ponto a partir da visão efetiva;
6. aprofundar rotinas operacionais de backup, restauração e LGPD.
