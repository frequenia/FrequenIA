# Prompt — FrequenIA — Fase 31: Governança e ciclo de vida biométrico

Implemente e homologue localmente a **Fase 31 — Governança e ciclo de vida biométrico** do FrequenIA.

Esta fase **não recria o reconhecimento facial**. O cadastro com múltiplas imagens, geração server-side do embedding ArcFace, comparação 1:1, liveness, mobile, quiosque, tentativas faciais e o workflow independente de `falha_facial` já existem e devem permanecer funcionais. O objetivo agora é fechar governança, desligamento, bloqueio, retenção, eliminação verificável, compatibilidade de modelo/limiar, transparência e resposta operacional a incidentes.

Trabalhe somente no repositório local. Não faça commit, push, merge, PR, deploy, provisionamento cloud, consulta a conta externa ou acesso à produção. Preserve integralmente todas as mudanças preexistentes do usuário.

## Contexto confirmado

- As migrations existentes vão de `001` a `025`; confirme isso antes de criar a próxima e use `026` sem renumerar arquivos.
- `biometrias.embedding` é hoje obrigatório, possui 512 dimensões e os estados `ativa`, `bloqueada` e `revogada`.
- Cadastro e recadastro revogam a biometria anterior e armazenam somente o embedding; as imagens de entrada são processadas em memória e não devem ser persistidas.
- A verificação é 1:1, tenant-scoped e usa identidade autenticada ou identidade resolvida pelo terminal; pesquisa facial global continua proibida.
- O desligamento atual do funcionário não conclui atomicamente o ciclo da biometria nem revoga todas as sessões vinculadas.
- O limiar `0.68` é um baseline do stack atual, não uma calibração corporativa homologada.
- `falha_facial` é um workflow operacional separado e não deve virar evento de retenção, incidente ou exclusão biométrica.
- Dados biométricos são dados pessoais sensíveis. Não invente base legal, prazo de retenção, hipótese de consentimento, encarregado, contato, RPO/RTO ou prazo jurídico de comunicação. Esses valores devem vir de política formal aprovada e configuração explícita.

## Fontes normativas e postura jurídica

Use como referência primária a LGPD e materiais oficiais da ANPD sobre biometria, segurança e comunicação de incidentes. Registre no relatório os links e a data de consulta. A implementação deve apoiar a decisão do controlador, não substituí-la.

- Não trate aceite de aviso como consentimento se essa não for a base legal formalmente aprovada.
- Não condicione o uso de biometria a uma base legal presumida pelo código.
- Não codifique permanentemente prazos jurídicos que possam mudar.
- Exija referência versionada à política aprovada e mantenha os valores de retenção configuráveis, validados e auditáveis.
- Se a política obrigatória estiver ausente ou inválida, novas operações sensíveis devem falhar de modo seguro, sem apagar automaticamente cadastros existentes.
- Comunicação externa de incidente exige decisão humana autorizada; o sistema prepara evidências sanitizadas e rastreáveis, mas não envia comunicação regulatória automaticamente.

## Regras de execução

Antes de editar:

1. leia `AGENTS.md` e os relatórios das Fases 25–30;
2. execute `git status --short` e registre quais mudanças já existiam;
3. inspecione as migrations `003`, `005`, `006`, `009`, `010`, `015`–`020` e `025`;
4. inspecione `routes/biometrics.py`, `routes/kiosk.py`, `routes/views.py`, `services/face_service.py`, autenticação/sessões, mobile, quiosque e suítes das Fases 10, 11, 14, 15 e 30;
5. confirme que `026` é a próxima migration disponível;
6. execute primeiro a suíte existente relevante e não esconda falhas preexistentes;
7. registre no relatório decisões, limitações e tudo que não pôde ser validado.

Use timestamps oficiais do PostgreSQL, UUIDs técnicos, transações, locks e constraints. Nenhum estado, política, prazo, identidade, modelo, limiar, decisão de liveness ou motivo enviado pelo cliente pode substituir a autoridade do servidor.

## Escopo obrigatório

### 1. Política biométrica versionada

- Criar uma representação versionada da política biométrica aprovada por empresa, com finalidade, referência da base legal aprovada externamente, versão do aviso, datas de vigência, prazo de retenção configurado, contato/rota de atendimento e responsável pela aprovação.
- Não armazenar parecer jurídico inteiro nem dado pessoal do aprovador; usar IDs técnicos e referência documental controlada.
- Impedir sobreposição de políticas vigentes para a mesma empresa e finalidade.
- Alterações são append-only ou versionadas; nunca reescrever a política que governou uma operação passada.
- Nova política não reativa biometria bloqueada, revogada ou eliminada.
- Produção deve rejeitar novo cadastro/recadastro quando não houver política vigente e aprovada; desenvolvimento/teste pode usar fixture explícita, nunca fallback silencioso.
- Expor readiness sanitizada da governança sem revelar tenant, documentos ou configurações sensíveis.

### 2. Perfil técnico de verificação

- Versionar perfil com modelo, versão do modelo, dimensão, métrica, limiar server-side, versão do liveness, status e vigência.
- Vincular cada biometria ao perfil usado no cadastro.
- Validar limites, dimensão e valores finitos no servidor e no banco quando aplicável.
- Perfil novo não altera retroativamente o perfil registrado na biometria.
- Não comparar embeddings incompatíveis. Exigir recadastro ou uma compatibilidade explicitamente aprovada, versionada e testada.
- Somente perfil aprovado e ativo pode ser usado em novo cadastro e verificação.
- Cliente nunca escolhe perfil, modelo, versão, limiar ou liveness.

### 3. Ciclo de vida e estados

- Criar migration incremental `026_biometric_governance_lifecycle.sql` após confirmar a numeração.
- Definir estados e transições explícitas para, no mínimo, ativa, bloqueada, revogada, exclusão pendente e eliminada.
- Tornar o embedding anulável somente no estado terminal de eliminação, com constraint que impeça biometria utilizável sem vetor ou eliminada com vetor.
- Registrar motivo codificado, timestamps do PostgreSQL, ator quando houver e política/perfil aplicável.
- Bloqueio impede imediatamente verificação, mobile e quiosque, sem apagar evidência necessária.
- Revogação é irreversível. Reativação exige novo cadastro; nunca reative silenciosamente vetor antigo.
- Eliminação remove irreversivelmente o embedding e qualquer referência privada associada, preservando apenas metadados mínimos não biométricos exigidos para prova do ciclo.
- Não expor embedding, imagem, referência física, score individual, hash sensível ou segredo por API, logs, métricas ou auditoria.

### 4. Desligamento, afastamento e sessões

- Centralizar a alteração de status do vínculo em serviço transacional reutilizado por todas as rotas existentes.
- Ao desligar um funcionário, bloquear/revogar imediatamente a biometria operacional e revogar as sessões daquele vínculo na mesma transação.
- Se houver política de retenção aplicável, agendar a eliminação; se não houver política aprovada, falhar de modo seguro e sinalizar pendência sem inventar prazo.
- Definir e documentar a política de `afastado`; ela deve ser configuração explícita do servidor e nunca decisão do cliente.
- Reativação do vínculo não reativa sessão nem biometria antiga automaticamente.
- Impedir corrida entre desligamento e verificação/cadastro com locks e revalidação dentro da transação relevante.
- Consultas 1:1 devem exigir vínculo operacionalmente permitido, biometria ativa, perfil compatível e política válida.

### 5. Retenção, hold e eliminação

- Implementar cálculo determinístico de elegibilidade a partir da política que governou o registro e de timestamps do PostgreSQL.
- Suportar hold formal e versionado que suspenda a eliminação, com justificativa não vazia, referência, autorização e expiração opcional.
- Hold nunca autoriza uso operacional de uma biometria bloqueada/revogada.
- Criar ferramenta administrativa tenant-scoped de retenção/eliminações, paginada, idempotente e concorrente com `FOR UPDATE SKIP LOCKED` ou mecanismo equivalente.
- A ferramenta deve ser `dry-run` por padrão e exigir flag explícita para executar.
- Falha parcial deve permanecer reprocessável, sem restaurar vetor eliminado.
- Concorrência não pode eliminar duas vezes, duplicar auditoria terminal ou deixar estado incompatível.
- Backups/restores e exercícios de continuidade não podem ressuscitar biometricamente um registro já eliminado no estado autoritativo. Documentar a estratégia e testar o que for possível localmente.

### 6. Solicitações e transparência

- Funcionário autenticado pode consultar somente o próprio estado biométrico, versão do aviso/política aplicável, finalidade e canal de atendimento, nunca o vetor ou scores.
- RH/admin da própria empresa podem consultar e operar o ciclo conforme autorização; gestor não administra biometria.
- Operações de bloqueio, revogação, hold, cancelamento de hold e solicitação de eliminação exigem motivo e idempotência.
- Cross-tenant, funcionário diferente e entidade fora do escopo retornam `404` não enumerável.
- Interface web e Flutter devem mostrar estados claros: ativa, bloqueada, recadastro necessário, exclusão pendente e eliminada.
- Não criar nova navegação nem redesign amplo; reutilizar telas existentes.
- O aviso deve explicar em linguagem simples finalidade, uso 1:1, ausência de pesquisa facial global, não persistência de fotos brutas no fluxo atual, retenção configurada e canal de atendimento, sem promessas jurídicas não aprovadas.

### 7. Auditoria e evidência

- Registrar cadastro, recadastro, bloqueio, revogação, desligamento, hold, liberação de hold, solicitação e conclusão de eliminação, mudança de política/perfil e incompatibilidade técnica.
- Auditoria deve ser transacional com a mudança autoritativa.
- Metadados permitem provar ação, estado anterior/novo, motivo codificado e versões técnicas/políticas, sem PII ou material biométrico.
- Consulta rotineira do próprio estado não deve poluir a auditoria.
- Histórico é append-only e não pode ser apagado pela eliminação do vetor.
- Ampliar a proteção de metadados contra chaves proibidas e objetos aninhados que contenham embedding, imagem, score individual, CPF, matrícula, token, caminho ou segredo.

### 8. Calibração e regressão técnica

- Criar harness local de calibração que aceite somente dataset sintético ou explicitamente autorizado fora do Git.
- Nunca versionar fotos, embeddings, scores individuais ou relatórios identificáveis.
- Produzir somente agregados documentados, incluindo distribuição, falsos aceites/rejeições conforme protocolo, tamanho da amostra, versão do modelo/liveness e limitações.
- O harness não promove limiar automaticamente. Promoção exige ato humano autorizado, perfil versionado e relatório anexado por referência.
- O baseline `0.68` deve permanecer identificado como não calibrado até existir evidência aprovada; não alegar precisão de produção com dados sintéticos.
- Testar comportamento por grupos apenas quando houver dataset autorizado e governança apropriada; não inferir atributo sensível a partir da face.
- Preservar validações de imagem, quantidade de faces, normalização, liveness e comparação 1:1.

### 9. Incidente e observabilidade

- Criar runbook de incidente biométrico com detecção, contenção, bloqueio, preservação de evidência, avaliação humana, recuperação, comunicação e pós-incidente.
- Não automatizar comunicação à ANPD ou titulares.
- Não hardcodar prazo regulatório; o runbook deve apontar a fonte oficial vigente e exigir confirmação pelo responsável antes de comunicar.
- Emitir métricas agregadas de operações, bloqueios, incompatibilidades, fila de eliminação, falhas e idade do backlog.
- Usar apenas dimensões de baixa cardinalidade; IDs de pessoa, empresa, biometria, sessão e política não podem ser dimensões.
- Logs e alertas não contêm PII, imagem, embedding, scores individuais, localização precisa ou referências privadas.
- Readiness deve detectar política/perfil ausente ou incompatível sem transformar liveness local em falsa garantia de conformidade.

### 10. Integração com fluxos existentes

- Mobile e quiosque continuam usando reconhecimento 1:1 e decisão server-side.
- Nenhum fluxo volta a aceitar identidade, embedding, threshold, liveness ou tipo de marcação enviados pelo cliente como autoridade.
- O motor de jornada da Fase 30 continua autoritativo para o evento de ponto.
- Geofence permanece no escopo da migration `020`, sem mudança funcional.
- `falha_facial` continua independente; eliminação/retenção biométrica não fecha nem cria ocorrência facial automaticamente.
- Marcações, tentativas e correções não são apagadas junto com o vetor biométrico.
- A marcação original, visão efetiva, exportações, anexos e continuidade das Fases 24–30 permanecem sem regressão.

## Testes obrigatórios — 70 critérios

### Política e perfil técnico

1. política biométrica vigente é resolvida por empresa e finalidade;
2. ausência de política bloqueia novo cadastro em modo equivalente a produção;
3. fixture de desenvolvimento/teste exige ativação explícita;
4. duas políticas vigentes sobrepostas são impedidas;
5. política passada permanece imutável e rastreável;
6. aviso/aceite não é persistido como consentimento presumido;
7. perfil técnico guarda modelo, versão, dimensão, métrica, limiar e liveness;
8. limiar inválido, não finito ou fora do limite falha fechado;
9. cliente não escolhe política, perfil, modelo, limiar ou liveness;
10. biometria fica vinculada às versões de política e perfil usadas no cadastro.

### Cadastro, compatibilidade e estados

11. cadastro continua exigindo funcionário ativo e tenant correto;
12. cadastro continua aceitando somente imagens válidas processadas em memória;
13. embedding enviado pelo cliente continua rejeitado;
14. recadastro revoga a biometria anterior e cria uma ativa;
15. duas inclusões concorrentes deixam exatamente uma biometria ativa;
16. perfil incompatível bloqueia verificação e solicita recadastro;
17. mudança de perfil não altera biometria histórica;
18. bloqueio impede imediatamente a verificação;
19. revogação é irreversível;
20. reativação exige novo cadastro e não reutiliza vetor antigo;
21. exclusão pendente não permite verificação;
22. estado eliminado exige embedding nulo e nenhuma referência privada;
23. estado utilizável exige embedding válido e perfil compatível;
24. transição inválida retorna conflito estável sem efeito parcial;
25. fotos brutas não são persistidas em sucesso ou falha.

### Desligamento, afastamento e concorrência

26. desligamento bloqueia/revoga a biometria na mesma transação;
27. desligamento revoga todas as sessões do vínculo na mesma transação;
28. falha no ciclo biométrico reverte o desligamento inteiro;
29. falha na revogação de sessão reverte o desligamento inteiro;
30. reativação não restaura sessão nem biometria;
31. política de afastamento é server-side, explícita e testada;
32. vínculo não operacional não consegue verificar pelo mobile;
33. vínculo não operacional não consegue verificar pelo quiosque;
34. corrida verificação × desligamento nunca confirma após o desligamento vencedor;
35. corrida cadastro × desligamento não deixa biometria ativa para desligado.

### Retenção, hold e eliminação

36. elegibilidade usa a política vinculada e timestamp do PostgreSQL;
37. prazo ausente não é substituído por default silencioso;
38. hold válido suspende a eliminação;
39. hold não restaura uso operacional;
40. hold exige justificativa e autorização tenant-scoped;
41. liberação de hold preserva histórico append-only;
42. dry-run não altera banco nem material biométrico;
43. execução explícita elimina vetor e referência privada;
44. eliminação preserva metadados mínimos e auditoria sanitizada;
45. eliminação repetida é idempotente;
46. duas purgas concorrentes processam o registro uma vez;
47. falha parcial permanece reprocessável sem estado impossível;
48. restore não torna utilizável um vetor já eliminado no estado autoritativo;
49. marcações, tentativas e correções sobrevivem à eliminação do vetor;
50. fila/backlog de eliminação é observável sem IDs de alta cardinalidade.

### Autorização, API, interface e auditoria

51. funcionário consulta somente o próprio estado e aviso aplicável;
52. resposta pessoal não expõe vetor, score, caminho ou referência privada;
53. gestor não administra nem consulta material biométrico;
54. RH/admin operam somente dentro da própria empresa;
55. cross-tenant e fora do escopo retornam `404` não enumerável;
56. operações mutáveis exigem motivo e idempotência;
57. auditoria é atômica com cada transição;
58. auditoria não contém PII, imagem, embedding, score, hash, caminho ou segredo, inclusive aninhados;
59. consulta pessoal rotineira não cria auditoria;
60. web e Flutter exibem estados e aviso sem material sensível.

### Segurança, incidente, migrations e regressão

61. harness de calibração rejeita dataset não autorizado ou dentro do Git;
62. relatório de calibração contém somente agregados e não promove limiar automaticamente;
63. runbook de incidente não envia comunicação externa e referencia fonte oficial vigente;
64. métricas e logs usam somente dimensões sanitizadas de baixa cardinalidade;
65. instalação limpa `001`–`026` passa em PostgreSQL real;
66. upgrade `001`–`025 → 026` preserva cadastros e tentativas existentes;
67. constraints, FKs, índices, transições e concorrência passam em PostgreSQL real;
68. regressões biométricas das Fases 10, 11, 14 e 15 e regressões das Fases 24–30 passam;
69. descoberta backend termina sem falhas e `flutter analyze` passa sem issues;
70. `flutter test` passa integralmente.

## Entregáveis

1. migration `026_biometric_governance_lifecycle.sql`;
2. serviço central de política, perfil técnico e ciclo biométrico;
3. desligamento/afastamento integrado a biometria e sessões;
4. API pessoal de transparência e APIs administrativas tenant-scoped;
5. retenção, hold e eliminação idempotente com dry-run;
6. proteção de auditoria contra dados biométricos e PII aninhados;
7. harness de calibração agregada sem dataset versionado;
8. interfaces web e Flutter ajustadas sem redesign amplo;
9. observabilidade e readiness sanitizadas;
10. runbook de incidente biométrico;
11. testes unitários, contratos, PostgreSQL real e concorrência;
12. CI opt-in para a integração da Fase 31;
13. matriz individual dos 70 critérios;
14. README, `.env.example` e `CONFIGURACAO_LOCAL.md` atualizados;
15. relatório `docs/FASE_31_GOVERNANCA_CICLO_BIOMETRICO.md`;
16. limitações reais e recomendações objetivas para a próxima fase.

## Critérios de aceite

A Fase 31 só termina quando:

- os 70 critérios estão mapeados para testes/evidências e passam;
- a biometria 1:1 existente permanece funcional sem pesquisa facial global;
- desligamento encerra atomicamente uso biométrico e sessões do vínculo;
- reativação não ressuscita sessão ou vetor anterior;
- política e perfil são versionados, explícitos e autoritativos no servidor;
- base legal, retenção e obrigação de comunicação não foram inventadas pelo código;
- perfil incompatível falha fechado e exige decisão explícita de recadastro/compatibilidade;
- hold suspende eliminação, mas nunca restaura uso operacional;
- eliminação zera o material biométrico de forma idempotente e auditável;
- backups/restores não reativam material já eliminado;
- APIs, interfaces, logs, métricas e auditoria não expõem material biométrico ou PII;
- isolamento tenant, RBAC, não enumeração e concorrência foram comprovados;
- `falha_facial`, jornada, geofence, marcações, correções, anexos e continuidade permanecem sem regressão;
- instalação limpa e upgrade até `026` passam em PostgreSQL real;
- backend, Flutter e testes obrigatórios terminam sem falhas;
- temporários são removidos após validação;
- não houve commit, push, merge, PR, deploy, provisionamento, conta AWS ou produção;
- o relatório distingue claramente evidência local, decisão jurídica pendente e homologação externa ainda necessária.

## Formato da resposta final

Apresente:

- resumo do que foi implementado;
- arquivos principais alterados;
- migrations e upgrades validados;
- resultado exato de cada suíte;
- matriz/relatório dos 70 critérios;
- garantias preservadas;
- decisões que dependem do controlador/jurídico/DPO;
- limitações e próximos passos;
- confirmação explícita de que não houve commit, push, PR, deploy, provisionamento ou acesso à produção.

Não declare conformidade LGPD, precisão de produção, base legal válida, prazo de retenção adequado ou homologação externa sem a evidência e a aprovação correspondentes.
