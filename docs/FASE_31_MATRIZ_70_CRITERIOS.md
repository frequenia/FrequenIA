# Matriz de aceite — Fase 31

Legenda: U = contrato/unitário; PG = PostgreSQL real; R = regressão; UI = interface.

| # | Evidência |
|---:|---|
| 1 | PG `test_policy_resolution_and_profile_are_server_authoritative` |
| 2 | PG `test_missing_policy_fails_closed_without_default_retention` |
| 3 | U `test_policy_is_versioned_append_only_and_overlap_is_checked`; não há fixture silenciosa |
| 4 | PG `test_policy_overlap_and_invalid_threshold_fail_in_database` |
| 5 | U migration append-only + PG upgrade preserva legado |
| 6 | U política não possui campo de consentimento |
| 7 | U `test_profile_has_all_server_side_technical_fields` |
| 8 | U/PG testes de limiar inválido/não finito |
| 9 | U `test_client_authority_fields_include_model_policy_and_threshold` |
| 10 | PG resolução e FKs compostas em `biometrias` |
| 11 | R Fases 10/15 + lock de funcionário ativo no cadastro |
| 12 | R Fase 15, processamento em memória |
| 13 | R Fases 10/11/15 rejeitam embedding do cliente |
| 14 | R Fase 15 + histórico `recadastrar` |
| 15 | PG `test_two_concurrent_enrollments_leave_exactly_one_active_biometric` + índice parcial e lock do vínculo |
| 16 | PG `test_verification_requires_active_link_policy_profile_and_exact_versions` |
| 17 | FK para perfil imutável na biometria; nenhuma atualização retroativa |
| 18 | PG transição para bloqueada + resolvedor aceita apenas ativa |
| 19 | PG `test_block_revoke_pending_are_irreversible_and_idempotent` |
| 20 | PG reativação do vínculo mantém biometria bloqueada/revogada |
| 21 | constraint/serviço: `exclusao_pendente` não verifica |
| 22 | U/PG constraint `eliminada` exige material nulo |
| 23 | resolvedor exige ativa, vetor, política e perfil compatíveis |
| 24 | PG transição inválida retorna `BiometricGovernanceError` sem commit |
| 25 | R Fases 10/15 e ausência de coluna de foto bruta |
| 26 | PG desligamento revoga biometria na transação |
| 27 | PG desligamento revoga duas sessões na transação |
| 28 | PG rollback do teste de desligamento preserva vínculo |
| 29 | serviço não commita; falha de sessão reverte transação chamadora |
| 30 | PG reativação não restaura biometria; sessões revogadas são irreversíveis |
| 31 | U/PG `BIOMETRIC_AWAY_POLICY` explícita e validada |
| 32 | resolvedor exige funcionário `ativo`; R mobile usa endpoint pessoal |
| 33 | resolvedor do quiosque exige vínculo ativo e governança |
| 34 | locks `FOR SHARE` × `FOR UPDATE` serializam verificação/desligamento |
| 35 | lock de vínculo + índice parcial impedem ativa para desligado |
| 36 | PG solicitação usa retenção da política vinculada e relógio do banco |
| 37 | PG ausência de política/retenção falha fechada |
| 38 | PG `test_hold_suspends_elimination_and_release_preserves_history` |
| 39 | hold não altera status nem resolvedor operacional |
| 40 | API admin/RH tenant-scoped exige motivo/referência |
| 41 | PG cancelamento preserva linha do hold |
| 42 | PG `test_dry_run_and_concurrent_purge_process_once` |
| 43 | PG eliminação zera embedding e referência privada |
| 44 | PG preserva biometria/histórico/auditoria sem material |
| 45 | PG eliminação repetida retorna zero elegíveis |
| 46 | PG dois executores somam uma eliminação |
| 47 | transação por lote mantém falha reprocessável; vetor eliminado nunca é restaurado |
| 48 | documentação exige reconciliação do estado autoritativo após restore |
| 49 | migration não altera FKs/tabelas de marcações, tentativas ou correções |
| 50 | evento agregado `deletion_pending/deleted/deletion_failed`, sem IDs como dimensão |
| 51 | API `GET /api/biometria/estado` deriva vínculo autenticado |
| 52 | U `test_personal_response_does_not_select_sensitive_material` |
| 53 | lifecycle/readiness/política/perfil permitem somente RH/admin |
| 54 | rotas usam exclusivamente `g.auth_context.empresa_id` |
| 55 | PG `test_cross_tenant_is_non_enumerable_at_service_boundary` e rotas 404 |
| 56 | operações mutáveis exigem motivo e chave de idempotência |
| 57 | histórico/auditoria usam o cursor da transação autoritativa |
| 58 | U/PG auditoria recursiva rejeita chaves sensíveis aninhadas |
| 59 | consulta pessoal não insere auditoria |
| 60 | UI perfil web/Flutter mostra cinco estados e aviso sem material |
| 61 | U harness exige autorização e dataset fora do Git |
| 62 | U saída agregada e `automatic_promotion=false` |
| 63 | runbook referencia LGPD/ANPD e proíbe comunicação automática |
| 64 | U observabilidade restringe dimensões de baixa cardinalidade |
| 65 | PG instalação limpa `001`–`026` |
| 66 | PG upgrade `001`–`025 → 026` preserva biometria legada |
| 67 | PG constraints/FKs/transições/concorrência (13 testes dedicados) |
| 68 | descoberta completa + regressões dedicadas Fases 25–31 |
| 69 | descoberta backend e `flutter analyze` |
| 70 | `flutter test` |
