# Prompt — FrequenIA — Fase 28: Fila assíncrona, observabilidade e continuidade dos anexos

Trabalhe no repositório FrequenIA e implemente a Fase 28 seguindo integralmente o `AGENTS.md` da raiz.

## Missão

Evoluir a varredura de anexos da Fase 27 para uma operação assíncrona, resiliente e observável, com:

1. fila SQS e DLQ declarativas;
2. outbox transacional e worker idempotente;
3. alarmes de backlog, quarentena e falhas;
4. monitoramento da atualização das assinaturas ClamAV;
5. lifecycle S3 conciliado com a retenção do PostgreSQL;
6. runbooks de incidente, reconciliação e continuidade;
7. testes de restauração usando somente recursos descartáveis.

Não realizar deploy, commit, push, provisionamento cloud ou acesso à produção. Entregar código, migrations, testes, documentação e infraestrutura declarativa validada localmente.

## Contexto confirmado

As Fases 24 a 27 já entregaram e homologaram:

- workflow de correções Gestor → RH;
- isolamento por empresa, escopo de gestor e não enumeração;
- marcação original imutável, visão efetiva e exportações;
- anexo privado PDF/JPEG/PNG de até 10 MiB;
- armazenamento local para teste e S3 compatível para produção;
- validação de conteúdo e autorização no backend;
- quarentena e ClamAV fail-closed;
- somente `ativo + limpo` disponível para download;
- retenção, purga idempotente e auditoria;
- observabilidade sanitizada e readiness;
- migrations `021` e `022`;
- CI local equivalente com PostgreSQL/pgvector, Moto S3 e ClamAV;
- relatório `docs/FASE_27_STORAGE_ANTIMALWARE_RETENCAO.md`.

Antes de alterar código:

1. leia `AGENTS.md` e os relatórios das Fases 25–27;
2. inspecione `git status` e preserve mudanças preexistentes;
3. confirme a última migration sem renumerar arquivos;
4. não leia `.env` nem use credenciais/recurso externo real;
5. mantenha os testes existentes como regressão obrigatória.

## Parte A — Outbox transacional

Criar migration incremental com uma tabela de jobs/outbox de varredura contendo, no mínimo:

- `id` UUID;
- `empresa_id`;
- `anexo_id`;
- versão do schema da mensagem;
- estado do job;
- número de tentativas de publicação/processamento;
- instante da próxima tentativa;
- timestamps do PostgreSQL;
- código de erro sanitizado;
- identificador opaco da mensagem publicada, quando existir.

Estados mínimos recomendados:

- `pendente_publicacao`;
- `publicado`;
- `processando`;
- `concluido`;
- `falha_reprocessavel`;
- `falha_terminal`.

Requisitos:

- criação do anexo em quarentena e criação do job ocorrem na mesma transação;
- unicidade impede dois jobs ativos equivalentes para o mesmo anexo;
- nenhum envio SQS ocorre antes do commit;
- dispatcher usa lock e `SKIP LOCKED` para múltiplas instâncias;
- falha de publicação permanece reprocessável;
- job publicado não é recriado por retry HTTP;
- payload da fila contém apenas IDs técnicos opacos e versão; não contém nome, CPF, matrícula, MIME, hash, bucket, chave ou caminho;
- PostgreSQL continua sendo a autoridade de estado e autorização.

## Parte B — SQS, DLQ e worker

### Fila

- Usar SQS Standard para distribuição de trabalho com semântica de entrega pelo menos uma vez.
- Declarar fila principal e DLQ separadas.
- Habilitar long polling.
- Configurar visibility timeout maior que o pior tempo permitido para a varredura.
- Configurar redrive com número de tentativas parametrizado e conservador.
- Habilitar criptografia; KMS CMK somente quando exigido por compliance e formalizado como decisão de custo/operação.
- Política da fila deve aplicar menor privilégio e proteção contra confused deputy quando houver service principal.
- Não enviar PII ou conteúdo do anexo na mensagem.

### Worker

- Implementar worker separado do processo web.
- Receber mensagens em lote pequeno e configurável.
- Validar estritamente versão e formato do payload.
- Recarregar anexo/job no PostgreSQL sob lock antes de agir.
- Tratar mensagens duplicadas e fora de ordem como operações idempotentes.
- Estender visibility timeout de forma controlada se a varredura puder ultrapassar o prazo inicial.
- Excluir mensagem somente após estado terminal persistido com sucesso.
- Em erro transitório, não excluir a mensagem.
- Em conteúdo infectado, persistir estado terminal e confirmar a mensagem.
- Mensagem inválida não pode liberar anexo; deve seguir política explícita de falha/DLQ.
- Encerramento deve parar polling, concluir ou abandonar seguramente o lote corrente e fechar clientes.
- Não usar thread em background dentro do Gunicorn para consumir a fila.

### Dispatcher

- Criar comando/processo idempotente para publicar outbox pendente.
- Usar cadeia padrão de credenciais do SDK.
- Reutilizar cliente SQS com timeout/retry limitado.
- Não capturar e ocultar falhas do SDK.
- Permitir execução contínua e execução única para testes/operação.

## Parte C — Compatibilidade local

- Desenvolvimento/teste deve possuir fila em memória ou adaptador controlado, nunca usada em produção.
- Produção deve rejeitar adaptador falso/local.
- CI deve usar SQS compatível descartável ou emulação determinística, além de PostgreSQL/pgvector, Moto S3 e ClamAV.
- O comportamento local precisa reproduzir duplicação, retry, visibility timeout e DLQ relevantes aos testes.

## Parte D — Observabilidade e alarmes

Publicar métricas de baixa cardinalidade, preferencialmente em EMF para o processo containerizado:

- jobs criados/publicados/concluídos/falhos;
- duração p90/p99 do processamento;
- idade do job mais antigo;
- anexos em quarentena além do prazo;
- mensagens visíveis/in-flight;
- mensagens na DLQ;
- falhas de storage, scanner e banco;
- idade das assinaturas ClamAV;
- divergências encontradas pela reconciliação.

Não usar usuário, empresa, anexo, job, request ou sessão como dimensão de métrica. IDs técnicos podem aparecer apenas em logs sanitizados, não como dimensões.

Declarar alarmes CloudWatch, sem aplicá-los:

- DLQ com mensagens;
- idade do job/mensagem acima do limite;
- quarentena atrasada;
- scanner indisponível;
- assinatura ClamAV desatualizada;
- taxa de falhas acima do limite;
- ausência de heartbeat do worker.

Requisitos dos alarmes:

- usar M-de-N quando aplicável;
- configurar `TreatMissingData` explicitamente;
- usar percentil para duração, nunca média;
- thresholds e destinos de notificação parametrizados/documentados;
- não criar assinatura de e-mail/SMS automaticamente;
- não incluir PII em nome, descrição ou dimensão.

## Parte E — Operação do ClamAV

- Consultar versão e data/idade das assinaturas por interface própria.
- Readiness do worker deve falhar quando assinaturas ultrapassarem limite configurado.
- Documentar `freshclam`/atualização como responsabilidade operacional separada do app.
- Não permitir que o backend atualize assinaturas por comando de usuário.
- Registrar somente versão, idade e resultado sanitizado.
- Adicionar teste com assinatura atual, desatualizada, ausente e resposta inválida.

## Parte F — Lifecycle S3 e retenção

O PostgreSQL continua sendo a autoridade da retenção de negócio.

- Não criar regra S3 que possa remover anexo ativo ou objeto antes de `retencao_ate`.
- Adicionar lifecycle seguro para abortar multipart uploads incompletos.
- Expiração automática de objetos só pode usar tag/prefixo de purga elegível aplicado após decisão persistida no banco e com margem de segurança documentada.
- Se a remoção continuar sendo feita pelo comando de purga, lifecycle funciona apenas como rede de segurança posterior.
- Não habilitar website, acesso público ou replicação não decidida.
- Manter documentada a decisão consciente sobre versionamento do bucket; se continuar desabilitado, registrar risco e compensações de continuidade.
- KMS CMK permanece condicional a requisito formal de compliance; não criar chave paga sem decisão explícita.

## Parte G — Reconciliação e continuidade

Criar comando read-only por padrão que compare PostgreSQL, fila/outbox e armazenamento:

- metadado sem objeto;
- objeto sem metadado;
- quarentena sem job ativo;
- job concluído com anexo não terminal;
- anexo limpo em prefixo incorreto;
- objeto elegível à purga ainda presente;
- divergência de tamanho/checksum.

Requisitos:

- modo padrão apenas relata;
- qualquer reparo exige flag explícita e operação específica;
- não apagar objeto desconhecido automaticamente;
- paginação obrigatória para listagens S3/SQS aplicáveis;
- saída e logs não exibem PII, conteúdo ou chave completa;
- produzir contagens e identificadores opacos para investigação.

Adicionar teste de continuidade totalmente descartável:

1. criar banco e objetos sintéticos;
2. produzir snapshot/backup local dos metadados necessários;
3. restaurar em nova base descartável;
4. executar reconciliação contra cópia isolada do storage;
5. comprovar que anexos limpos autorizados continuam íntegros;
6. comprovar que quarentena/infectados continuam bloqueados;
7. remover todos os recursos temporários.

Não acessar backup real e não implementar política corporativa completa de disaster recovery nesta fase.

## Parte H — Runbooks

Criar runbooks para:

- fila com backlog;
- mensagens na DLQ e redrive controlado;
- scanner indisponível;
- assinaturas desatualizadas;
- storage indisponível;
- detecção de malware;
- divergência de reconciliação;
- restauração e validação de continuidade;
- rollback de configuração sem liberar anexos inseguros.

Cada runbook deve conter sintomas, métricas, diagnóstico, contenção, recuperação, validação e evidência a preservar. Comandos destrutivos devem ser claramente marcados e nunca executados automaticamente.

## Testes obrigatórios

### Outbox e publicação

1. upload e job são atômicos;
2. rollback não publica job;
3. retry HTTP não duplica job;
4. dispatcher publica pendente após commit;
5. falha de publicação permanece reprocessável;
6. dois dispatchers não publicam o mesmo job duas vezes;
7. payload contém somente campos permitidos;
8. versão desconhecida é rejeitada;
9. produção rejeita fila falsa/local;
10. cliente SDK usa cadeia padrão, timeout e retry limitado.

### Worker e SQS

11. mensagem válida processa anexo em quarentena;
12. mensagem duplicada é idempotente;
13. mensagem fora de ordem não reabre terminal;
14. limpo fica disponível;
15. infectado fica bloqueado e confirma mensagem;
16. falha transitória não confirma mensagem;
17. persistência falha não confirma mensagem;
18. mensagem só é excluída após commit terminal;
19. visibility timeout é maior que o timeout do scan;
20. extensão de visibility é limitada;
21. poison message não libera arquivo e alcança DLQ;
22. worker encerra sem corromper o lote;
23. concorrência de workers não duplica scan/promoção;
24. web não executa consumidor em background.

### Métricas, alarmes e ClamAV

25. métricas não usam dimensão de alta cardinalidade;
26. logs/EMF não contêm campos proibidos;
27. duração usa percentil no alarme;
28. alarmes usam M-de-N e missing-data explícito;
29. DLQ dispara condição de alarme;
30. backlog/quarentena atrasada são mensuráveis;
31. heartbeat ausente falha condição de alarme;
32. assinatura atual mantém readiness;
33. assinatura desatualizada falha readiness;
34. assinatura ausente/inválida falha fechada;
35. aplicação não executa atualização arbitrária de assinatura.

### Lifecycle, reconciliação e continuidade

36. lifecycle nunca expira ativo;
37. multipart incompleto possui expiração declarada;
38. purge-eligible respeita banco e margem;
39. versionamento possui decisão e risco documentados;
40. reconciliação encontra metadado sem objeto;
41. reconciliação encontra objeto sem metadado;
42. reconciliação encontra quarentena sem job;
43. reconciliação encontra divergência de checksum/tamanho;
44. modo padrão não altera nada;
45. reparo exige flag explícita;
46. listagem usa paginação;
47. restauração preserva anexo limpo íntegro;
48. restauração mantém quarentena/infectado bloqueado;
49. temporários são removidos ao final;
50. runbooks cobrem os oito incidentes definidos.

### Segurança e regressão

51. fila e DLQ são privadas e criptografadas;
52. políticas de service principal usam proteção contra confused deputy quando aplicável;
53. nenhuma mensagem contém PII ou chave do objeto;
54. cross-tenant e fora do escopo permanecem 404;
55. somente `ativo + limpo` baixa;
56. marcação original permanece inalterada;
57. visão efetiva e exportações permanecem corretas;
58. suítes das Fases 25–27 permanecem verdes;
59. `falha_facial` permanece independente;
60. `flutter analyze` e `flutter test` passam.

## Infraestrutura declarativa

Atualizar ou criar templates com:

- SQS principal e DLQ;
- redrive policy;
- criptografia;
- long polling;
- visibility timeout parametrizado;
- queue policy mínima, quando necessária;
- IAM de runtime/worker separado por responsabilidade;
- alarmes e dashboard mínimos;
- lifecycle S3 reconciliado;
- outputs documentados;
- `DeletionPolicy`/`UpdateReplacePolicy` adequados para recursos stateful.

Validar com `cfn-lint` e, se disponível, `cfn-guard`. Não executar change set ou deploy.

Para política IAM derivada do código Python, usar IAM Policy Autopilot e tratar sua saída como baseline: revisar e rejeitar permissões genéricas ou incompatíveis com os recursos declarados. Nunca fazer upload da política sem autorização.

## Restrições

- Não acessar ou alterar produção.
- Não provisionar SQS, S3, KMS, SNS, CloudWatch ou qualquer recurso real.
- Não executar deploy, commit, push, merge ou PR.
- Não apagar/restaurar mudanças preexistentes do usuário.
- Não enviar conteúdo, PII, hash ou chave do objeto para a fila.
- Não confirmar mensagem antes do commit terminal.
- Não liberar arquivo por falha, timeout, duplicação ou mensagem inválida.
- Não executar worker dentro do Gunicorn.
- Não criar KMS CMK ou assinatura SNS sem decisão explícita.
- Não usar lifecycle S3 como autoridade de retenção.
- Não executar correção destrutiva da reconciliação por padrão.
- Não implementar push, XLSX, espelho de ponto, escalas avançadas ou redesign.
- Não alterar estados/transições do workflow de correções nem a marcação original.

## Validação final

Executar e registrar:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Executar separadamente as integrações PostgreSQL das Fases 25–28 com todos os serviços descartáveis documentados.

Em `mobile/`:

```powershell
flutter analyze
flutter test
```

Validar templates e contratos de CI sem criar recursos externos. Se o run remoto continuar indisponível por falta de commit/push autorizado, registrar explicitamente a pendência.

## Entrega

Atualizar README, configuração local, `.env.example`, migrations, infraestrutura, CI e política operacional de anexos.

Criar `docs/FASE_28_FILA_OBSERVABILIDADE_CONTINUIDADE.md` contendo:

1. decisão arquitetural da fila;
2. modelo de entrega, retry e DLQ;
3. migration/outbox;
4. dispatcher e worker;
5. métricas, alarmes e dashboard;
6. operação das assinaturas ClamAV;
7. lifecycle e retenção;
8. reconciliação;
9. teste de continuidade/restauração;
10. runbooks;
11. IAM e infraestrutura declarativa;
12. testes executados e resultados exatos;
13. limitações;
14. itens recomendados para a Fase 29.

Não declarar a Fase 28 concluída enquanto houver confirmação prematura de mensagem, possibilidade de download inseguro, job sem recuperação, DLQ sem alarme, métrica com PII/alta cardinalidade, lifecycle conflitante com o banco, restauração não testada, regressão ou teste obrigatório falhando.
