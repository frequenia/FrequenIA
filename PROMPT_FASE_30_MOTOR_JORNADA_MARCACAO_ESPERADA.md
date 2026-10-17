# Prompt — FrequenIA — Fase 30: Motor de jornada, marcação esperada e exceções de ordem

Trabalhe no repositório FrequenIA e implemente a Fase 30 seguindo integralmente o `AGENTS.md` da raiz.

## Missão

Completar o fluxo automático de ponto para que o backend, e nunca o cliente, determine a marcação esperada a partir da jornada vigente, escala da data, histórico e visão efetiva. Entregar:

1. motor determinístico de jornada diária;
2. escalas/exceções por data e folgas;
3. próxima marcação calculada no servidor;
4. suporte operacional a múltiplos períodos e virada de dia;
5. preservação auditada de tentativas sem jornada ou fora da sequência;
6. concorrência e idempotência por evento esperado;
7. UI web e Flutter sem escolha autoritativa do tipo;
8. regressões completas das Fases 24–29.

Não realizar deploy, commit, push, merge, PR, acesso à produção ou alteração de recurso cloud. Não implementar geolocalização nova, folha de pagamento, banco de horas, adicional noturno ou cálculo jurídico de horas nesta fase.

## Contexto confirmado

Já existem e devem ser preservados:

- `turnos`, `periodos_turno` e `funcionarios_turnos` desde a migration `004`;
- múltiplos períodos, validação de sobreposição e `fim_dia_offset`;
- histórico de atribuição por vigência;
- consulta de jornada própria e administrativa;
- marcações `entrada`, `saida_intervalo`, `retorno_intervalo` e `saida`;
- intervalo mínimo, idempotência e lock por funcionário;
- marcação facial mobile e quiosque;
- geofence existente da migration `020`, sem expansão de escopo;
- visão efetiva das correções sem alteração da marcação original;
- ocorrência `ordem_invalida` disponível no domínio;
- biometria 1:1, liveness e workflow independente de `falha_facial`;
- migrations `001`–`024` e homologações das Fases 24–29.

Lacuna principal confirmada: mobile e quiosque ainda enviam `tipo`, e o backend aceita essa escolha. A Fase 30 deve retirar essa autoridade do cliente.

Antes de editar:

1. leia `AGENTS.md` e os relatórios das Fases 25–29;
2. execute `git status --short` e preserve todas as mudanças preexistentes;
3. inspecione migrations `004`, `007`, `008`, `014`, `016`–`020` e `024`;
4. inspecione `utils/schedules.py`, APIs de jornada, rotas mobile/quiosque, visão efetiva e testes das Fases 8, 9, 14 e 24–29;
5. confirme que a próxima migration é `025`, sem renumerar as existentes;
6. documente qualquer decisão funcional que não possa ser inferida com segurança.

## Parte A — Contrato do motor de jornada

Criar um serviço de domínio único, reutilizado por mobile, quiosque, área pessoal e gestão, que receba no mínimo:

- empresa e funcionário autenticados;
- instante oficial do PostgreSQL;
- timezone IANA da jornada;
- atribuição vigente;
- escala/exceção específica da data;
- períodos aplicáveis;
- marcações efetivas já reconhecidas para a jornada operacional.

O serviço deve produzir:

- data operacional da jornada;
- origem da jornada (`turno`, `escala`, `troca`, `folga` ou `sem_jornada`);
- eventos esperados ordenados;
- próximo evento esperado;
- estado (`aguardando`, `em_andamento`, `concluida`, `folga`, `sem_jornada`, `excecao`);
- motivo técnico sanitizado quando não houver próximo evento;
- snapshot/versionamento suficiente para reprodução histórica.

Mapeamento mínimo dos períodos:

- início do primeiro período → `entrada`;
- fim de período que não seja o último → `saida_intervalo`;
- início de período posterior → `retorno_intervalo`;
- fim do último período → `saida`.

Para mais de dois períodos, repetir alternadamente saída e retorno, preservando a ordem. Não inferir o tipo a partir de texto, índice enviado pelo cliente ou última seleção da UI.

## Parte B — Jornada operacional e timezone

- Tratar a jornada como uma unidade operacional, mesmo quando termina no dia seguinte.
- Período iniciado antes da meia-noite e encerrado depois dela pertence à data operacional de início.
- Consultas feitas após meia-noite devem localizar primeiro uma jornada anterior ainda aberta antes de abrir a jornada do novo dia.
- Usar `ZoneInfo` e o timezone do turno; não fixar `America/Sao_Paulo` no motor.
- Definir e testar política explícita para horários locais inexistentes ou ambíguos por mudança de offset/DST; nunca normalizar silenciosamente.
- Timestamps oficiais e decisões concorrentes devem usar o relógio do PostgreSQL.
- Alteração posterior de turno/escala não pode reescrever o snapshot de uma jornada que já recebeu tentativa ou marcação.

## Parte C — Escala e exceção por data

Criar migration incremental `025` após confirmar a numeração. Modelar escala diária/exceção sem apagar o histórico.

Suportar:

- uso normal do turno vigente;
- turno diferente em uma data específica;
- folga em uma data específica;
- cancelamento lógico de uma escala futura;
- origem `escala`, `troca` ou `ajuste`;
- justificativa administrativa não vazia para troca/ajuste/cancelamento;
- criação/alteração somente por administrador ou RH da empresa;
- gestor apenas consulta funcionários dentro do próprio escopo;
- funcionário consulta somente a própria escala;
- conflito de duas escalas ativas para a mesma pessoa/data impedido no banco;
- escala passada ou jornada já iniciada não pode ser reescrita; correção ocorre por novo registro/histórico autorizado.

Prioridade obrigatória:

1. escala/exceção ativa da data;
2. turno do funcionário vigente na data;
3. `sem_jornada`.

Não implementar recorrência complexa, troca solicitada pelo funcionário, aprovação trabalhista ou banco de horas sem requisito adicional.

## Parte D — Snapshot diário e eventos esperados

Persistir um snapshot técnico e imutável da jornada diária quando ela for consultada para marcar ou receber a primeira tentativa relevante.

O snapshot deve conter apenas dados de jornada necessários, incluindo:

- IDs técnicos e tenant;
- funcionário;
- data operacional e timezone;
- origem e referência ao turno/escala;
- versão;
- eventos esperados com ordem, tipo e instante esperado;
- timestamps do PostgreSQL.

Requisitos:

- unicidade por empresa/funcionário/data operacional;
- eventos únicos por snapshot/ordem;
- nenhuma cópia de nome, CPF, matrícula ou dado biométrico;
- histórico não é atualizado retroativamente;
- criação concorrente resulta em um único snapshot;
- evento cumprido referencia a marcação original sem alterá-la;
- correção aprovada deve ser considerada pela visão efetiva, sem regravar a marcação original;
- snapshot não deve se tornar uma segunda fonte divergente para relatórios.

## Parte E — Próxima marcação calculada pelo servidor

Criar endpoint pessoal e reutilizável para consultar a próxima marcação, por exemplo `GET /api/marcacoes/proxima`, sem aceitar `empresa_id`, `funcionario_id`, tipo ou horário autoritativo do cliente.

Resposta mínima:

- estado da jornada;
- data operacional;
- próximo tipo/label quando aplicável;
- horário esperado;
- ordem e total de eventos;
- indicador de atraso/adiantamento apenas informativo;
- motivo sanitizado quando bloqueada ou enviada para análise.

Mobile e quiosque devem registrar sem selecionar o tipo. Durante compatibilidade:

- se `tipo` legado ainda for recebido, ele não pode ter autoridade;
- divergência entre tipo legado e tipo calculado deve ser rejeitada ou ignorada segundo política documentada, nunca aceita silenciosamente;
- novo frontend não deve enviar `tipo`;
- respostas continuam retornando o tipo decidido pelo servidor.

## Parte F — Registro confirmado e tolerâncias

- A marcação deve usar o próximo evento esperado calculado dentro da mesma transação/lock.
- O horário registrado continua sendo o instante real do servidor, não o horário planejado.
- Chegar cedo ou tarde não muda automaticamente o tipo; diferenças temporais devem ser registradas para relatórios futuros.
- Tolerâncias são parâmetros server-side, informativas nesta fase, e não podem gerar cálculo jurídico ou desconto.
- Intervalo mínimo já homologado permanece obrigatório.
- Idempotência deve considerar operação, pessoa e evento esperado.
- Duas requisições concorrentes para o mesmo evento: somente uma cria a marcação; a outra reutiliza idempotentemente ou recebe conflito coerente.
- Marcação administrativa/importada continua em fluxo separado e autorizado.

## Parte G — Sem jornada, folga e fora de ordem

Quando não houver evento esperado válido, não descartar a tentativa e não criar marcação confirmada arbitrária.

Tratar no mínimo:

- funcionário sem turno/escala;
- folga;
- jornada já concluída;
- marcação extra;
- lacuna ou inconsistência no snapshot;
- tentativa incompatível com tipo legado;
- jornada anterior ainda aberta;
- mudança administrativa concorrente.

O comportamento deve:

- preservar a tentativa técnica relevante;
- criar ou reutilizar uma ocorrência `ordem_invalida` tenant-scoped quando análise humana for necessária;
- impedir ocorrências duplicadas para o mesmo ciclo/evento;
- retornar código HTTP e `codigo` estáveis;
- nunca transformar a exceção em marcação confirmada automaticamente;
- permitir decisão pela gestão usando o workflow existente ou extensão mínima compatível;
- manter `falha_facial` como fluxo separado;
- permitir que uma correção aprovada alimente a visão efetiva sem mudar o original.

Defina claramente quais casos apenas informam `folga/sem_jornada` e quais abrem ocorrência; não gerar ocorrência por simples consulta.

## Parte H — Autorização e auditoria

- Funcionário consulta apenas a própria jornada e próxima marcação.
- Gestor consulta somente equipe/unidade autorizada.
- RH e administrador ficam limitados à empresa autenticada.
- Cross-tenant e fora do escopo retornam `404` não enumerável.
- Cliente não escolhe empresa, pessoa, timezone, snapshot, evento ou tipo.
- Auditar criação/cancelamento de escala, materialização de snapshot, exceção de ordem, vinculação do evento e decisão administrativa.
- Auditoria não inclui CPF, nome, matrícula, imagem, embedding, localização precisa, token ou payload facial.
- Consultas pessoais rotineiras não devem gerar ruído auditável desnecessário.

## Parte I — Interfaces

### Flutter

- Remover o seletor de tipo da marcação facial.
- Exibir a próxima marcação retornada pelo servidor.
- Mostrar estados simples: próxima marcação, jornada concluída, folga, sem jornada e enviado para análise.
- Atualizar a próxima marcação após sucesso, conflito idempotente ou análise.
- Não criar nova navegação.

### Quiosque web

- Remover o seletor manual de tipo.
- Após identificar matrícula e validar face, usar a decisão server-side.
- Limpar sessão/dados após o resultado, como já homologado.
- Não mostrar detalhes da jornada de outra pessoa além do necessário para a operação atual.

### Gestão web

- Reutilizar a tela de jornadas para escala/folga por data e consulta do histórico.
- Gestor permanece somente leitura quando essa for a política atual.
- Evitar redesign amplo.

## Parte J — Observabilidade

Emitir eventos/métricas sanitizados e de baixa cardinalidade para:

- jornada resolvida por turno/escala/folga/ausência;
- criação e conflito de snapshot;
- próximo evento calculado;
- marcação confirmada por tipo;
- atraso/adiantamento agregados;
- exceção de ordem;
- concorrência/idempotência;
- falhas do motor e timezone inválido.

Não usar pessoa, empresa bruta, snapshot, marcação ou ocorrência como dimensão. Não registrar horários individuais completos em log operacional quando uma métrica agregada for suficiente.

## Testes obrigatórios

### Motor e calendário

1. primeiro início gera `entrada`;
2. primeiro fim intermediário gera `saida_intervalo`;
3. início posterior gera `retorno_intervalo`;
4. último fim gera `saida`;
5. quatro períodos geram oito eventos na ordem correta;
6. períodos sobrepostos continuam rejeitados;
7. ordem não sequencial continua rejeitada;
8. período com menos de 24 horas atravessa meia-noite corretamente;
9. jornada noturna pertence à data operacional de início;
10. consulta após meia-noite encontra jornada anterior aberta;
11. novo dia só abre quando a jornada anterior não é aplicável;
12. timezone do turno é usado;
13. horário local inexistente/ambíguo segue política explícita;
14. ausência de jornada retorna estado estável sem inventar tipo.

### Escalas, histórico e snapshot

15. turno vigente é usado sem escala específica;
16. escala da data tem prioridade sobre turno vigente;
17. troca de turno por data preserva justificativa/histórico;
18. folga da data não cria eventos esperados;
19. cancelamento lógico futuro restaura a regra inferior aplicável;
20. duas escalas ativas na mesma data são impedidas;
21. escala cross-tenant é não enumerável;
22. funcionário não cria nem altera escala;
23. gestor fora do escopo não consulta escala;
24. RH/admin atuam somente na própria empresa;
25. jornada iniciada não pode ter snapshot reescrito;
26. duas materializações concorrentes criam um snapshot;
27. eventos do snapshot são únicos e ordenados;
28. snapshot não contém PII ou biometria.

### Próxima marcação e autoridade

29. endpoint pessoal deriva identidade da autenticação;
30. cliente não escolhe empresa, funcionário ou timezone;
31. cliente novo não envia tipo;
32. tipo legado divergente não ganha autoridade;
33. servidor retorna tipo decidido;
34. horário registrado é o instante real do PostgreSQL;
35. adiantamento não altera o tipo esperado;
36. atraso não altera o tipo esperado;
37. tolerância inválida falha segura;
38. marcação administrativa continua separada e autorizada;

### Concorrência, ordem e exceções

39. primeiro evento confirmado avança a jornada;
40. sequência completa termina em `concluida`;
41. intervalo mínimo continua bloqueando repetição imediata;
42. mesma idempotency key reutiliza a operação correta;
43. mesma chave com operação diferente retorna conflito;
44. duas conexões concorrentes criam uma marcação para o evento;
45. tentativa extra após jornada concluída não cria confirmada;
46. tentativa em folga não cria confirmada;
47. tentativa sem jornada não cria confirmada;
48. exceção preserva tentativa técnica;
49. ocorrência `ordem_invalida` é criada somente quando aplicável;
50. repetição do mesmo ciclo não duplica ocorrência;
51. `falha_facial` permanece workflow independente;
52. exceção nunca altera marcação original.

### Visão efetiva, interfaces e observabilidade

53. correção aprovada participa da sequência efetiva;
54. correção rejeitada/cancelada não participa;
55. visão efetiva e exportações permanecem coerentes;
56. Flutter exibe próxima marcação sem seletor manual;
57. Flutter exibe concluída, folga, sem jornada e análise;
58. quiosque não oferece seletor de tipo;
59. gestão permite escala/folga sem nova navegação;
60. logs/auditoria não contêm PII, biometria ou localização precisa;
61. métricas usam dimensões de baixa cardinalidade;
62. consulta rotineira não polui auditoria;

### Migrations, segurança e regressão

63. instalação limpa `001`–`025` passa;
64. upgrade `001`–`024 → 025` preserva turnos, atribuições e marcações;
65. constraints, FKs e índices impedem inconsistências tenant/data;
66. regressões das Fases 8, 9 e 14 passam;
67. regressões das Fases 24–29 passam;
68. descoberta backend termina sem falhas;
69. `flutter analyze` passa sem issues;
70. `flutter test` passa integralmente.

## Validação PostgreSQL obrigatória

Usar PostgreSQL/pgvector real e descartável para validar:

- instalação limpa e upgrade;
- múltiplos períodos e virada de dia;
- materialização concorrente do snapshot;
- duas marcações concorrentes para o mesmo evento;
- escala versus turno vigente;
- folga e ausência de jornada;
- ocorrência fora de ordem sem duplicação;
- visão efetiva com correções;
- isolamento por empresa e escopo do gestor;
- preservação byte a byte da marcação original.

Usar relógio controlável no serviço para testes unitários, mas confirmar timestamps oficiais e locks no PostgreSQL real. Remover banco e recursos descartáveis após a validação.

## Fora de escopo

- folha de pagamento, banco de horas e cálculos trabalhistas;
- adicional noturno, horas extras e descontos;
- feriados nacionais obtidos por serviço externo;
- troca de turno solicitada/aprovada pelo funcionário;
- geofence nova ou mudança das regras da migration `020`;
- notificações push;
- relatórios XLSX e espelho de ponto;
- mudança do modelo biométrico;
- governança final da retenção biométrica;
- assinatura/publicação do APK;
- deploy, produção ou recurso cloud real.

## Entrega

Entregar:

1. decisão do motor e política de exceções;
2. migration incremental `025`;
3. serviço único de resolução da jornada;
4. escalas/folgas por data com histórico;
5. snapshot diário e eventos esperados;
6. endpoint de próxima marcação;
7. registro mobile/quiosque sem autoridade do tipo no cliente;
8. ocorrência `ordem_invalida` idempotente;
9. concorrência e auditoria;
10. UI web e Flutter atualizadas;
11. observabilidade sanitizada;
12. CI e testes unitários/integração/concorrência;
13. matriz individual dos 70 critérios;
14. documentação local atualizada;
15. relatório `docs/FASE_30_MOTOR_JORNADA_MARCACAO_ESPERADA.md`;
16. limitações e recomendações para a Fase 31.

O relatório final deve declarar resultados exatos, skips explícitos, migrations exercitadas, recursos temporários removidos e confirmar que não houve commit, push, PR, deploy ou acesso à produção.
