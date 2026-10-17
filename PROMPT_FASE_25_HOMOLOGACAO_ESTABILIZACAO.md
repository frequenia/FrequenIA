# Prompt — FrequenIA — Fase 25: Homologação e estabilização do workflow de correções

Trabalhe no repositório FrequenIA e conclua a Fase 25 seguindo integralmente o `AGENTS.md` da raiz.

## Missão

Homologar e estabilizar o workflow de correções de ponto Gestor → RH implementado na Fase 24. A entrega deve demonstrar, com testes reais em PostgreSQL e validação das interfaces, que o fluxo é seguro, concorrente, auditável, isolado por empresa e adequado ao piloto.

Não redesenhe o workflow e não expanda a fase com novas funcionalidades de produto.

## Contexto confirmado

Já existem:

- `services/correction_workflow.py`;
- `supabase/migrations/018_correction_manager_hr_workflow.sql`;
- endpoints pessoais e administrativos em `routes/occurrences.py`;
- visão efetiva em `services/effective_timekeeping.py`;
- UI administrativa com timeline;
- acompanhamento web e Flutter;
- testes unitários da Fase 24;
- RBAC, isolamento por empresa e escopo de gestor;
- exportações que devem continuar usando a visão efetiva;
- workflow independente de ocorrências `falha_facial`.

## Trabalho obrigatório

1. Antes de editar, inspecione o estado do Git e preserve alterações existentes.
2. Revise a implementação atual e relacione cada critério do `AGENTS.md` a uma evidência de código ou teste.
3. Prepare PostgreSQL descartável para testes, aplicando as migrations em ordem.
4. Crie testes de integração para todo o workflow, inclusive cross-tenant, escopo do gestor, auditoria, visão efetiva e exportação.
5. Crie testes concorrentes reais com duas conexões independentes e sincronização determinística. Não simule concorrência apenas com mocks.
6. Confirme que somente uma decisão vence e que o conflito retorna 409.
7. Confirme que a marcação original nunca é atualizada e que o ajuste aparece apenas na visão efetiva.
8. Corrija quaisquer defeitos encontrados, mantendo regras de domínio centralizadas no serviço.
9. Faça a descoberta padrão de testes ser reproduzível. Testes que dependem de ambiente externo devem exigir opt-in ou produzir `skip` explícito.
10. Corrija o teste de configuração para refletir as variáveis oficiais atuais de EmailJS e TomTom.
11. Execute a suíte backend completa apropriada, registrando quantidade de testes, sucessos, skips e falhas.
12. Execute `flutter analyze` e `flutter test`; diagnostique problemas reproduzíveis do projeto.
13. Atualize o README com configuração, migrations, comandos de teste e checklist de homologação.
14. Registre anexos de correção como limitação, sem criar armazenamento nesta fase.

## Restrições

- Não acessar nem alterar produção.
- Não usar credenciais reais em código, testes, documentação ou logs.
- Não executar deploy.
- Não alterar marcações originais.
- Não permitir decisão direta do RH antes de `encaminhada_rh`.
- Não permitir que funcionário aprove, rejeite ou encaminhe.
- Não enfraquecer escopo de gestor, isolamento de empresa ou não enumeração.
- Não misturar o workflow de correções com o workflow de `falha_facial`.
- Não implementar anexos, push, XLSX, espelho de ponto, escalas avançadas ou redesign.
- Não apagar alterações preexistentes do usuário.
- Não realizar commit, push ou abrir PR sem pedido explícito.

## Validação mínima esperada

Ao final, execute e informe os resultados de:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Execute também a suíte de integração PostgreSQL pelo comando documentado no projeto e, em `mobile/`:

```powershell
flutter analyze
flutter test
```

Se algum comando não puder ser executado, não declare sucesso. Explique o bloqueio, preserve as evidências e deixe o comando exato para reprodução.

## Formato da entrega

Apresente:

1. resumo do que foi homologado;
2. arquivos alterados;
3. migrations verificadas;
4. cenários de integração e concorrência cobertos;
5. resultado das suítes backend e Flutter;
6. confirmação de preservação da marcação original;
7. confirmação de isolamento por empresa e escopo do gestor;
8. limitações restantes;
9. itens recomendados para a Fase 26.

Não considere a fase concluída enquanto houver falha de teste, erro de importação, concorrência não testada em PostgreSQL ou Flutter não validado.
