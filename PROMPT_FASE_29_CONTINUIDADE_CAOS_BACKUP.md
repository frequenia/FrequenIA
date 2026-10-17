# Prompt — FrequenIA — Fase 29: Continuidade operacional, caos controlado e governança de backup

Trabalhe no repositório FrequenIA e implemente a Fase 29 seguindo integralmente o `AGENTS.md` da raiz.

## Missão

Transformar os mecanismos locais de continuidade da Fase 28 em uma disciplina operacional reproduzível e segura, com:

1. política técnica de backup e restauração com RPO/RTO configuráveis e aprovação formal pendente quando necessário;
2. conjuntos de backup versionados por manifesto, íntegros e verificáveis;
3. exercícios periódicos de restore e redrive somente em ambientes isolados;
4. testes de caos determinísticos para banco, storage, fila, worker e scanner;
5. automação controlada da elegibilidade `purge-eligible` após commit e retenção vencida;
6. medição de capacidade, recuperação e evidências operacionais sanitizadas;
7. regras `cfn-guard`, contratos CloudFormation e runbooks atualizados.

Não realizar deploy, commit, push, merge, PR, provisionamento cloud, acesso à produção nem uso de dados pessoais reais. Entregar código, migration incremental, testes, documentação e infraestrutura declarativa validada localmente.

## Contexto confirmado

As Fases 24 a 28 já homologaram localmente:

- workflow Gestor → RH, isolamento por empresa e não enumeração;
- marcação original imutável, visão efetiva e exportações;
- anexos privados, quarentena, ClamAV fail-closed, retenção e purga;
- storage S3 compatível e adaptador local restrito a desenvolvimento/teste;
- outbox transacional, SQS Standard, DLQ e worker idempotente;
- observabilidade sanitizada, alarmes declarativos e readiness;
- reconciliação dry-run e um exercício descartável de restauração;
- migrations `001`–`023` e regressões das Fases 24–28.

Antes de alterar código:

1. leia `AGENTS.md` e os relatórios das Fases 25–28;
2. execute `git status --short` e preserve todas as mudanças preexistentes;
3. inspecione migrations, outbox, worker, storage, scanner, purga, reconciliação, observabilidade, CI e template AWS;
4. confirme que a próxima migration é posterior à `023`, sem renumerar nenhuma existente;
5. registre limitações reais do ambiente em vez de simular validações indisponíveis.

## Parte A — Política e modelo de continuidade

Produza uma decisão arquitetural que diferencie claramente:

- backup operacional;
- snapshot ou exportação de teste;
- restauração;
- exercício de continuidade;
- disaster recovery;
- alta disponibilidade;
- retenção legal/operacional;
- versionamento de objetos.

Defina parâmetros server-side para RPO, RTO, frequência, retenção, janela de exercício e tamanho máximo do conjunto. Os valores de produção devem permanecer explicitamente pendentes de aprovação do responsável quando não houver decisão formal. Valores locais servem apenas ao teste e não podem ser apresentados como compromisso corporativo.

Classifique no mínimo:

- PostgreSQL e migrations;
- objetos privados dos anexos;
- manifestos e evidências;
- configurações sem segredo;
- filas/outbox e estados reprocessáveis;
- dados biométricos, deixando claro que sua política jurídica continua separada.

Não copiar `.env`, credenciais, tokens, caches, logs brutos ou temporários para o conjunto de backup.

## Parte B — Manifesto e conjunto verificável

Criar um formato de manifesto versionado contendo somente metadados técnicos necessários:

- versão do schema;
- identificador opaco do exercício/conjunto;
- ambiente lógico;
- timestamps do servidor;
- componentes incluídos;
- migrations aplicadas;
- quantidade e tamanho agregado;
- checksums dos artefatos;
- método de criptografia esperado;
- resultado de verificação;
- parâmetros RPO/RTO usados no exercício.

Requisitos:

- nenhum CPF, nome, matrícula, e-mail, conteúdo de anexo, segredo, URL ou chave completa;
- checksum validado antes da restauração;
- manifesto adulterado, incompleto ou de versão desconhecida deve falhar fechado;
- conjunto parcial nunca pode ser declarado restaurável;
- escrita temporária deve usar diretório isolado, permissões restritivas e limpeza segura;
- backup não deve ser salvo no Git, em `static/` ou em diretório público;
- criptografia em repouso deve ser declarada; chaves reais não entram no repositório;
- usar dados sintéticos e chaves efêmeras somente nos testes descartáveis.

## Parte C — Migration e trilha operacional

Criar migration incremental `024` se a inspeção confirmar essa numeração. Persistir apenas controle e evidência sanitizada, nunca o backup ou conteúdo do objeto.

Modelar, conforme necessário:

- execuções de backup/restore/redrive/caos;
- tipo de exercício;
- estado (`planejado`, `executando`, `concluido`, `falha_reprocessavel`, `falha_terminal`, `cancelado`);
- IDs técnicos opacos;
- início/fim e timestamps do PostgreSQL;
- contagens, bytes agregados, duração e resultado sanitizado;
- RPO/RTO observados;
- responsável técnico por ID interno/papel, sem PII duplicada;
- versão do manifesto e evidência de integridade;
- histórico append-only e auditoria.

Aplicar constraints, FKs, índices, isolamento por empresa quando o evento for tenant-scoped e concorrência segura. Validar instalação limpa `001`–`024` e upgrade representativo `001`–`023 → 024`.

## Parte D — Backup e restauração descartáveis

Implementar ferramentas administrativas separadas para preparar, verificar e restaurar conjuntos sintéticos. Preferir operações explícitas, não interativas e reproduzíveis.

Obrigatório:

- dry-run/planejamento por padrão;
- execução exige flag explícita;
- destino deve ser uma base e storage descartáveis validados;
- recusar produção, origem/destino iguais e destinos não vazios sem autorização específica;
- nunca interpolar credenciais ou nomes fornecidos pelo usuário em shell inseguro;
- não registrar comandos contendo senha;
- exportar PostgreSQL em formato adequado à restauração e verificar retorno/integridade;
- inventariar objetos esperados pelo banco sem aceitar chave arbitrária do operador;
- restaurar primeiro em isolamento, aplicar validações e somente então marcar o exercício como concluído;
- garantir que anexo em quarentena continue bloqueado e que somente `ativo + limpo` permaneça baixável;
- manter outbox pendente retomável após restore;
- remover apenas recursos descartáveis criados pelo próprio teste, em bloco `finally` e com alvos exatos conferidos.

Não chamar o exercício local de backup operacional de produção.

## Parte E — Redrive controlado

Criar um procedimento e ferramenta administrativa para simular e validar redrive da DLQ em ambiente isolado.

- read-only/plan por padrão;
- execução exige autorização explícita, motivo e limite de lote;
- validar schema e IDs técnicos antes de redrive;
- rejeitar mensagem adulterada, desconhecida ou cross-tenant;
- não permitir alteração manual do resultado do scanner;
- não reabrir job terminal válido nem duplicar scan, objeto ou auditoria;
- registrar origem, destino, contagem e resultado de forma sanitizada;
- preservar mensagem problemática/evidência até confirmação do redrive;
- interromper com segurança diante de taxa de falha ou dependência indisponível;
- documentar critérios de entrada, saída e rollback.

SQS Standard continua com semântica de pelo menos uma vez. Redrive não transforma o sistema em exactly-once; a garantia permanece na idempotência do domínio.

## Parte F — Caos controlado

Criar um harness de falhas determinístico e restrito a testes. Ele não pode ser ativado em produção, por payload do cliente ou por variável ambígua.

Cobrir no mínimo:

- PostgreSQL indisponível antes e depois do commit;
- storage indisponível, lento ou com objeto/checksum divergente;
- SQS indisponível, duplicação, atraso, fora de ordem e DLQ;
- worker encerrado antes do scan, após scan e antes/depois do ack;
- scanner indisponível, timeout, resposta desconhecida e assinatura vencida;
- manifesto truncado/adulterado;
- conjunto de backup parcial;
- restore interrompido e retomado;
- dispatcher e workers concorrentes;
- relógio controlado para testar RPO, retenção e alarmes sem depender do tempo real.

Cada falha deve possuir invariante verificável: nenhum download indevido, nenhuma perda silenciosa, nenhum efeito duplicado, estado reprocessável quando seguro e evidência sanitizada.

## Parte G — Capacidade e recuperação

Criar teste de carga sintético e limitado, sem dados pessoais e sem atacar serviço externo.

Medir:

- throughput de publicação e consumo;
- p50, p95 e p99 de espera e processamento;
- crescimento e drenagem do backlog;
- tempo de recuperação depois de indisponibilidade;
- comportamento com múltiplos workers;
- taxa de retry, DLQ e erro;
- CPU/memória quando disponível sem exigir privilégio global.

Os limites devem ser configuráveis e os resultados devem ser apresentados como evidência local, não como garantia de produção. Não executar carga ilimitada, não usar endpoints públicos e não incluir IDs de usuário/tenant como dimensão.

## Parte H — Elegibilidade de purga

Automatizar de forma controlada a aplicação da tag `frequenia-purge-eligible=true` somente quando:

- o registro existe e foi validado no PostgreSQL;
- não está ativo;
- retenção venceu;
- purga foi autorizada/persistida;
- objeto corresponde ao tamanho/checksum esperado;
- nenhuma restauração ou investigação ativa o preserva.

Usar padrão pós-commit/outbox ou mecanismo equivalente recuperável. Exigir idempotência, lote, retomada, auditoria, dry-run por padrão e flag explícita para mutação. Falha de tag não pode apagar objeto nem marcar purga como concluída. Nunca aceitar chave arbitrária, nunca listar/alterar outro prefixo e nunca aplicar tag em anexo ativo, quarentena válida ou retry.

## Parte I — Observabilidade e objetivos

Evoluir métricas sanitizadas para incluir:

- idade do último backup verificável;
- duração p95/p99 de backup e restore;
- RPO/RTO observado no exercício;
- último exercício concluído;
- falha de integridade do manifesto;
- falha e progresso de redrive;
- caos iniciado/concluído apenas em teste;
- capacidade de drenagem do backlog;
- divergência e aplicação de `purge-eligible`.

Regras:

- dimensões somente de baixa cardinalidade;
- `TreatMissingData` explícito;
- M-de-N quando apropriado;
- heartbeat usa ausência como falha;
- métricas esparsas de erro usam ausência como não violação;
- latência usa percentis, não média isolada;
- thresholds de produção não podem ser inventados a partir de uma única execução local;
- dashboard e runbooks devem indicar quais valores exigem calibração em homologação.

## Parte J — Infraestrutura, `cfn-guard` e IAM

Atualizar infraestrutura declarativa sem aplicar recursos reais.

- avaliar versionamento S3 e documentar a decisão completa de retenção/custo antes de habilitar;
- se habilitado, tratar versões não correntes sem permitir exclusão prematura;
- manter bloqueio público, TLS, criptografia, ownership enforced, `DeletionPolicy` e `UpdateReplacePolicy` coerentes;
- KMS CMK somente se compliance formal exigir; não provisionar chave nesta fase sem decisão;
- declarar recursos/condições necessários à observabilidade e exercícios sem criar assinatura SNS;
- IAM separado por backup, restore, redrive, tagging e leitura de evidências;
- menor privilégio por ARN/prefixo, sem permissões genéricas desnecessárias;
- proteger service principals com `aws:SourceAccount` e `aws:SourceArn` quando aplicável;
- adicionar regras locais `cfn-guard` versionadas para os controles críticos do projeto;
- executar `cfn-lint` e `cfn-guard` se disponíveis;
- se `cfn-guard` não estiver instalado, não instalar sem autorização: manter testes de contrato equivalentes e registrar a limitação.

Não executar change set, `describe-events`, deploy ou consulta a conta AWS real.

## Parte K — Runbooks e evidências

Atualizar ou criar runbooks para:

1. backup atrasado ou inválido;
2. restauração interrompida;
3. RPO/RTO observado acima do objetivo;
4. redrive seguro da DLQ;
5. corrupção ou divergência de objeto;
6. indisponibilidade prolongada de banco, fila, storage ou scanner;
7. esgotamento de capacidade/backlog;
8. tag `purge-eligible` incorreta ou atrasada;
9. rollback do exercício e preservação de evidência;
10. aprovação e revisão periódica da política.

Cada runbook deve conter sinais, impacto, pré-condições, papéis autorizados, triagem, contenção, execução, validação, rollback, evidências e proibições. Nunca recomendar bypass de scanner, autorização, retenção, auditoria ou uso de dados reais em teste.

## Testes obrigatórios

### Política, manifesto e migration

1. política diferencia backup, snapshot, restore, continuidade e DR;
2. valores de produção não aprovados permanecem explicitamente pendentes;
3. configuração inválida de RPO/RTO/retention falha segura;
4. manifesto possui versão e ID opaco;
5. manifesto não contém PII, segredo, conteúdo, URL ou chave completa;
6. checksum válido é aceito;
7. manifesto adulterado é rejeitado;
8. versão desconhecida é rejeitada;
9. conjunto parcial não é declarado restaurável;
10. migration limpa `001`–`024` passa;
11. upgrade `001`–`023 → 024` preserva dados;
12. constraints, índices, timestamps e histórico são válidos.

### Backup e restore

13. planejamento/dry-run não altera estado;
14. execução exige flag explícita;
15. origem ou destino de produção é recusado;
16. origem e destino iguais são recusados;
17. destino não vazio é recusado sem autorização específica;
18. credenciais não aparecem em comando, log ou manifesto;
19. PostgreSQL sintético é exportado e restaurado;
20. objetos sintéticos são inventariados e restaurados;
21. checksum de banco/objetos é conferido antes da conclusão;
22. quarentena restaurada continua indisponível;
23. somente `ativo + limpo` restaurado pode baixar;
24. outbox pendente volta a ser processável;
25. restore interrompido permanece retomável ou falha terminal segura;
26. temporários descartáveis são removidos com alvo exato.

### Redrive e idempotência

27. plano de redrive não move mensagens;
28. execução exige autorização, motivo e lote;
29. payload inválido é rejeitado sem liberar anexo;
30. mensagem cross-tenant não é redirecionada;
31. job terminal não é reaberto;
32. duplicata não duplica scan, objeto, estado ou auditoria;
33. falha transitória interrompe redrive de forma segura;
34. mensagem/evidência é preservada até confirmação;
35. redrive concluído registra somente dados sanitizados;
36. duas execuções concorrentes não processam o mesmo item duas vezes.

### Caos e recuperação

37. falha do banco antes do commit não publica trabalho órfão;
38. falha após commit mantém trabalho recuperável;
39. storage indisponível mantém download bloqueado;
40. checksum divergente falha fechado;
41. SQS indisponível preserva outbox;
42. duplicação/fora de ordem não regride estado;
43. worker encerrado antes do ack permite reprocessamento idempotente;
44. scanner timeout/erro/estado desconhecido bloqueia;
45. assinatura vencida bloqueia readiness segura;
46. backup truncado/adulterado não restaura;
47. restore interrompido não é marcado concluído;
48. falhas injetáveis são impossíveis fora de teste;
49. relógio controlado produz resultados determinísticos;
50. nenhuma falha entrega bytes indevidos ou perde evento silenciosamente.

### Capacidade, observabilidade e purga

51. carga sintética é limitada e não usa serviço externo;
52. throughput e p50/p95/p99 são medidos;
53. crescimento e drenagem do backlog são medidos;
54. recuperação após indisponibilidade é medida;
55. métricas usam dimensões de baixa cardinalidade;
56. alarmes usam M-de-N e missing-data explícito quando aplicável;
57. heartbeat ausente pode alarmar;
58. erro esparso ausente não alarma indevidamente;
59. threshold local não é apresentado como SLO de produção;
60. dry-run de tagging não altera objeto;
61. anexo ativo nunca recebe `purge-eligible`;
62. retenção futura/quarentena/retry nunca recebem a tag;
63. elegível recebe tag somente após commit e validação;
64. falha de tagging permanece reprocessável e não conclui purga;

### Infraestrutura, segurança e regressão

65. regras `cfn-guard` cobrem público, HTTP, criptografia, retenção e filas;
66. `cfn-lint` e contratos CloudFormation passam;
67. IAM de backup/restore/redrive/tagging segue menor privilégio;
68. regressões das Fases 24–28 permanecem verdes;
69. `flutter analyze` passa sem issues;
70. `flutter test` passa integralmente.

## Validação final

Executar, conforme disponibilidade local e sem acesso externo real:

1. instalação limpa de migrations `001`–`024`;
2. upgrade representativo `001`–`023 → 024`;
3. descoberta completa do backend;
4. integrações PostgreSQL das Fases 25–29;
5. S3 e SQS compatíveis descartáveis;
6. ClamAV descartável com EICAR e verificação de assinatura;
7. exercício de backup/restore/redrive e caos com dados sintéticos;
8. concorrência com conexões/processos independentes quando aplicável;
9. validação CloudFormation e regras de compliance locais;
10. secret scanning;
11. `flutter analyze`;
12. `flutter test`.

Skips de integrações opt-in devem ser explícitos na descoberta padrão e executados sem skip nas suítes dedicadas/CI. Diferenciar claramente teste local, contrato de emulador e comportamento que somente uma homologação cloud autorizada pode confirmar.

## Entrega

Entregar:

- código e migration incremental;
- ferramentas administrativas seguras;
- harness de caos restrito a testes;
- regras `cfn-guard` e contratos CloudFormation;
- runbooks atualizados;
- documentação de configuração local;
- matriz dos 70 critérios com evidência por teste;
- relatório `docs/FASE_29_CONTINUIDADE_CAOS_BACKUP.md`;
- limitações reais e recomendações objetivas para a Fase 30.

O relatório final deve declarar explicitamente:

- tudo que foi executado e seus resultados;
- RPO/RTO observados apenas no ambiente descartável;
- decisões ainda pendentes de aprovação corporativa;
- ferramentas indisponíveis;
- recursos temporários removidos;
- que não houve commit, push, PR, deploy, provisionamento ou acesso à produção.
