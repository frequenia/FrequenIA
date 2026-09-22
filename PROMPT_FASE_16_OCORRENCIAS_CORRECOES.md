# Prompt para Codex — Fase 16: Ocorrências e Correções de Ponto

Continue a implementação do FrequenIA no repositório `frequenia/FrequenIA`.

Branch base e consolidada: `desenvolvimento-mvp`.

## Contexto confirmado no repositório

O projeto já possui autenticação JWT, sessões persistentes, RBAC, isolamento por empresa, jornadas, marcações manuais e faciais, biometria 1:1, liveness, Controle de Ponto e exportações CSV, PDF e DOCX.

As migrations históricas já incluem:

- `007_clock_events.sql`, com `tentativas_faciais` e `marcacoes`;
- `008_occurrences_corrections.sql`, com `ocorrencias` e `correcoes`;
- `009_notifications_audit.sql`, com `notificacoes` e `auditoria`;
- `010_indexes_constraints.sql`, com índices dessas estruturas.

O fluxo funcional de ocorrências e correções ainda não está implementado. Não existem APIs pessoais ou administrativas para esse domínio, não existe visão efetiva das marcações e o Controle de Ponto ainda consulta diretamente apenas `marcacoes`.

Existe um rascunho Flutter em `mobile/lib/requests/requests_page.dart`, mas ele chama contratos inexistentes (`/solicitacoes` e `/ocorrencias`) e não está conectado à navegação. Adapte esse código ao contrato oficial somente depois que a API estiver definida e testada.

Antes de alterar qualquer arquivo:

1. inspecione `git status`, branch e alterações locais;
2. preserve qualquer trabalho não commitado do usuário;
3. leia as migrations `007`, `008`, `009` e `010` completas;
4. confirme os contratos atuais de autenticação em `utils/auth_decorator.py`;
5. entenda a consulta central do Controle de Ponto em `routes/timekeeping.py`;
6. execute os testes existentes em ambiente com as dependências instaladas;
7. não refaça autenticação, marcações, biometria ou jornadas sem necessidade.

---

## Objetivo

Implementar um fluxo auditável de solicitação, análise, aprovação, rejeição e aplicação lógica de correções de ponto.

Fluxo esperado:

```text
marcação original
→ solicitação de ocorrência/correção
→ análise por gestor, RH ou administrador
→ aprovação ou rejeição
→ correção aprovada registrada separadamente
→ visão efetiva passa a considerar o ajuste
```

A marcação original deve permanecer imutável em `marcacoes`.

Não implementar nesta fase regras trabalhistas completas, folha de pagamento, banco de horas, fechamento mensal ou workflow com múltiplos níveis.

---

## 1. Modelagem e migration incremental

Reutilize `ocorrencias` e `correcoes`. Não crie tabelas paralelas e não edite migrations históricas.

Analise a incompatibilidade entre os tipos atuais e as categorias funcionais exigidas. As solicitações devem preservar pelo menos uma destas categorias:

- `esquecimento_marcacao`;
- `horario_incorreto`;
- `tipo_incorreto`;
- `justificativa`;
- `outro`.

Os valores técnicos de `correcoes.tipo` (`inclusao`, `alteracao_instante`, `alteracao_tipo`, `justificativa`) podem continuar representando a operação aplicada, mas a categoria informada pelo solicitante também precisa ficar auditável.

Se faltar campo ou restrição essencial, crie uma migration incremental numerada após a última migration existente, por exemplo:

```text
012_occurrence_correction_workflow.sql
```

A migration deve, conforme necessário:

- adicionar a categoria funcional da solicitação;
- manter campos de decisão e observação auditáveis;
- criar índices para listagens por empresa, funcionário, estado e data;
- garantir uma regra determinística para correções aprovadas sobre a mesma marcação;
- preservar `timestamptz`;
- evitar qualquer `UPDATE` ou `DELETE` destrutivo em `marcacoes`.

Estados funcionais:

```text
pendente → aprovada
pendente → rejeitada
pendente → cancelada
```

É permitido mapear `pendente` para o estado histórico `solicitada`, desde que o contrato da API seja consistente e as transições sejam centralizadas. Depois de aprovada, rejeitada ou cancelada, a solicitação não pode ser decidida novamente.

---

## 2. API pessoal

Implemente um blueprint ou módulo próprio, evitando aumentar ainda mais `routes/views.py`.

### Criar solicitação

```http
POST /api/ocorrencias
```

Perfis autenticados permitidos:

- `funcionario`;
- `gestor`;
- `rh`;
- `administrador`.

Essa rota é sempre pessoal: empresa, usuário e funcionário vêm exclusivamente da sessão.

Payload:

```json
{
  "tipo": "horario_incorreto",
  "marcacao_id": "uuid-opcional",
  "motivo": "Registrei o ponto depois de resolver uma falha no aplicativo.",
  "instante_solicitado": "2026-09-12T08:02:00-03:00",
  "tipo_marcacao_solicitado": "entrada"
}
```

Rejeite campos controlados pelo servidor, incluindo:

- `empresa_id`;
- `funcionario_id`;
- `usuario_id`;
- `estado` ou `status`;
- analisador, decisão e timestamps administrativos.

Valide por categoria:

- `esquecimento_marcacao`: sem marcação original, com instante e tipo solicitados;
- `horario_incorreto`: marcação original e instante solicitado;
- `tipo_incorreto`: marcação original e tipo solicitado;
- `justificativa`: motivo obrigatório, podendo não alterar horário ou tipo;
- `outro`: motivo obrigatório e combinação coerente dos campos opcionais.

Quando houver `marcacao_id`, confirme com uma única consulta limitada por `empresa_id` e `funcionario_id`. Um ID de outra empresa ou de outro funcionário deve produzir a mesma resposta usada para um ID inexistente.

Rejeite datetime ingênuo. Exija offset explícito ou `Z` e normalize para um objeto timezone-aware antes de enviar ao PostgreSQL.

### Consultar solicitações próprias

```http
GET /api/ocorrencias
GET /api/ocorrencias/<ocorrencia_id>
```

Filtros da listagem:

- `status`;
- `inicio`;
- `fim`.

Retorne somente registros do funcionário autenticado na empresa autenticada.

### Cancelar

```http
POST /api/ocorrencias/<ocorrencia_id>/cancelar
```

Somente o solicitante pode cancelar, e somente enquanto a solicitação estiver pendente. Faça a transição dentro de transação com lock.

---

## 3. API de gestão

Perfis autorizados:

- `administrador`;
- `gestor`;
- `rh`.

Todas as consultas devem incluir `empresa_id` da sessão. Não confie em empresa informada pelo navegador.

### Listagem e detalhe

```http
GET /api/gestao/ocorrencias
GET /api/gestao/ocorrencias/<ocorrencia_id>
```

Filtros:

- `funcionario_id`;
- `status`;
- `tipo`;
- `inicio`;
- `fim`.

O detalhe deve apresentar:

- funcionário e matrícula;
- categoria, motivo e estado;
- marcação original, quando houver;
- instante e tipo originais;
- instante e tipo solicitados;
- solicitante e data da solicitação;
- analisador, decisão, observação e data da análise.

### Aprovar

```http
POST /api/gestao/ocorrencias/<ocorrencia_id>/aprovar
```

Payload:

```json
{
  "observacao": "Ajuste aprovado após validação com a liderança."
}
```

Dentro de uma única transação:

1. busque a solicitação por ID e empresa com `SELECT ... FOR UPDATE`;
2. responda como inexistente quando pertencer a outro tenant;
3. confirme que continua pendente;
4. valide novamente a marcação original e os valores solicitados;
5. registre analisador e `clock_timestamp()` do PostgreSQL;
6. marque a correção como aprovada;
7. grave auditoria;
8. crie notificação para o solicitante;
9. faça commit.

Não altere nenhuma coluna da marcação original.

### Rejeitar

```http
POST /api/gestao/ocorrencias/<ocorrencia_id>/rejeitar
```

Exija observação não vazia. Use o mesmo padrão de transação, lock, isolamento de tenant, auditoria e notificação da aprovação.

Somente uma decisão pode vencer. Uma segunda tentativa deve retornar conflito sem alterar a decisão anterior.

---

## 4. Visão efetiva das marcações

Crie uma camada reutilizável no backend, preferencialmente em `services/` ou `utils/`, que seja a única responsável por combinar marcações e correções aprovadas.

Comportamento:

- marcação sem correção aprovada mantém horário e tipo originais;
- `alteracao_instante` aprovada substitui logicamente o instante;
- `alteracao_tipo` aprovada substitui logicamente o tipo;
- justificativa sem alteração não muda horário nem tipo;
- solicitação pendente, rejeitada ou cancelada não muda a visão;
- inclusão aprovada gera um evento efetivo virtual;
- evento virtual deve ter origem explícita, como `ajuste_administrativo`;
- nenhum evento virtual pode fingir origem facial ou possuir tentativa facial inventada.

Cada item efetivo deve preservar metadados suficientes para auditoria, por exemplo:

```json
{
  "id": "id-logico",
  "marcacao_original_id": "uuid-ou-null",
  "correcao_id": "uuid-ou-null",
  "instante": "2026-09-12T11:02:00Z",
  "tipo": "entrada",
  "origem": "ajuste_administrativo",
  "ajustada": true
}
```

Defina e teste o comportamento quando existirem solicitações concorrentes para a mesma marcação. A visão efetiva nunca pode depender de ordem acidental de consulta.

---

## 5. Controle de Ponto e exportações

Altere `routes/timekeeping.py` para consumir a camada efetiva.

Requisitos:

- manter a agregação diária atual;
- preservar filtros por dia civil em `America/Sao_Paulo`;
- não aplicar deslocamento de timezone duas vezes;
- manter o cálculo atual de total, sem criar regras trabalhistas;
- fazer CSV, PDF e DOCX refletirem a mesma visão efetiva;
- incluir marcações esquecidas aprovadas;
- ignorar solicitações pendentes, rejeitadas e canceladas;
- opcionalmente devolver `ajustada: true` para a interface mostrar `Ajustado`.

Não consulte `ponto`, `presenca`, `horarios` ou outras tabelas legadas.

---

## 6. Interface web de gestão

Crie uma página própria, seguindo o padrão visual atual:

```text
/ocorrencias
```

Adicione o acesso ao menu somente para administrador, gestor e RH.

A página deve permitir:

- listar solicitações;
- filtrar por funcionário, status, categoria e período;
- abrir o detalhe;
- comparar valor original e solicitado;
- visualizar motivo;
- informar observação;
- aprovar;
- rejeitar;
- atualizar a listagem depois da decisão;
- exibir erros sem revelar dados de outro tenant.

Não redesenhe o restante do painel.

No Controle de Ponto, mostre um indicador discreto `Ajustado` quando a API informar que o evento foi corrigido.

---

## 7. Interface pessoal Flutter

Depois da estabilização da API, adapte `mobile/lib/requests/requests_page.dart`:

- usar exclusivamente `/api/ocorrencias`;
- alinhar o payload ao contrato oficial;
- enviar datetime com offset explícito;
- listar solicitações próprias e seus estados;
- abrir formulário de nova solicitação;
- permitir cancelamento pendente, se implementado;
- conectar a página à navegação autenticada.

Não altere o fluxo facial mobile.

Se a UI Flutter ampliar excessivamente o escopo, conclua primeiro backend, gestão web, visão efetiva e testes, deixando a pendência descrita claramente no relatório final.

---

## 8. Auditoria e notificações

Reutilize as tabelas existentes. Registre no mínimo:

- `ocorrencia.criada`;
- `ocorrencia.cancelada`;
- `ocorrencia.aprovada`;
- `ocorrencia.rejeitada`.

Não grave tokens, imagens, embeddings, CPF, senha ou segredos em `auditoria.metadados`.

Crie notificações para aprovação e rejeição. Se já houver uma API pessoal de notificações em desenvolvimento, integre sem duplicá-la; caso não exista, implemente somente o mínimo necessário e documente o contrato.

---

## 9. Testes obrigatórios

Adicione testes unitários e de integração compatíveis com o padrão atual.

### Criação

- funcionário cria para si;
- identidade vem da sessão;
- `empresa_id`, `funcionario_id`, estado e analisador no payload são rejeitados;
- marcação deve pertencer ao funcionário e empresa autenticados;
- ID de outro tenant não vaza dados;
- categoria inválida retorna 400;
- datetime ingênuo retorna 400;
- validações específicas de cada categoria.

### Consulta e RBAC

- funcionário vê somente as próprias solicitações;
- administrador, gestor e RH veem somente a empresa autenticada;
- funcionário não acessa a API de gestão;
- filtros de status, categoria e datas funcionam;
- UUID inválido retorna 400;
- ID válido de outro tenant retorna 404 ou o padrão equivalente do projeto.

### Decisão e concorrência

- cada perfil de gestão autorizado consegue aprovar e rejeitar;
- funcionário não decide;
- aprovação e rejeição registram analisador e timestamp do banco;
- observação é obrigatória na rejeição;
- segunda decisão retorna conflito;
- duas decisões concorrentes resultam em apenas uma vencedora;
- marcação original permanece byte a byte inalterada nos campos funcionais.

### Visão efetiva

- alteração de horário aprovada aparece;
- alteração de tipo aprovada aparece;
- justificativa não altera horário ou tipo;
- pendente, rejeitada e cancelada não alteram a visão;
- marcação esquecida aprovada aparece como evento virtual;
- origem do evento virtual é administrativa;
- Controle de Ponto usa a visão efetiva;
- CSV, PDF e DOCX usam a visão efetiva;
- resultado é determinístico diante de solicitações conflitantes.

### Timezone

- offset explícito é aceito;
- datetime ingênuo é rejeitado;
- correção próxima da meia-noite cai no dia civil correto;
- UTC é convertido uma única vez para São Paulo;
- filtros civis geram limites UTC corretos.

### Regressão

Execute também os testes existentes de:

- login, refresh e logout;
- RBAC e tenant isolation;
- jornadas;
- marcação manual;
- biometria e liveness;
- marcação facial;
- Controle de Ponto e exportações;
- Flutter, quando o SDK estiver disponível.

---

## 10. Restrições obrigatórias

Não quebrar:

- `/api/marcacoes`;
- `/api/marcacoes/facial`;
- autenticação e refresh token;
- jornadas;
- biometria e reconhecimento 1:1;
- liveness;
- Controle de Ponto;
- exportações;
- aplicativo mobile.

Não:

- atualizar ou apagar marcações originais para aplicar correção;
- confiar em IDs administrativos enviados pelo cliente;
- acessar Supabase diretamente pelo frontend;
- alterar timezone armazenado no banco;
- criar marcação facial falsa;
- inventar tentativa facial;
- reativar busca facial global;
- editar migrations históricas já aplicadas;
- incluir regras trabalhistas, folha ou banco de horas.

---

## Critérios de aceite

A fase estará concluída somente quando:

1. o funcionário conseguir criar, consultar e acompanhar a própria solicitação;
2. gestão conseguir listar, detalhar, aprovar e rejeitar;
3. transições forem transacionais e protegidas por lock;
4. somente uma decisão puder vencer;
5. a marcação original nunca for modificada pela correção;
6. a correção aprovada alterar a visão efetiva;
7. solicitações pendentes, rejeitadas e canceladas não alterarem a visão;
8. inclusão aprovada aparecer como ajuste administrativo;
9. Controle de Ponto e exportações usarem a mesma visão efetiva;
10. RBAC e tenant isolation estiverem cobertos por testes;
11. timezone continuar correto;
12. auditoria registrar todas as transições relevantes;
13. testes novos e de regressão passarem;
14. fluxos facial e mobile permanecerem íntegros.

---

## Relatório final obrigatório

Ao terminar, informe:

1. arquivos alterados;
2. migrations reutilizadas e criadas;
3. endpoints adicionados;
4. payloads e respostas principais;
5. transições de estado implementadas;
6. como a concorrência foi protegida;
7. como a marcação original permanece preservada;
8. como funciona a visão efetiva;
9. como Controle de Ponto e exportações foram integrados;
10. RBAC e isolamento de tenant;
11. tratamento de timezone;
12. auditoria e notificações;
13. testes adicionados;
14. comandos executados e resultados;
15. limitações restantes.

Implemente a fase por completo, faça as correções necessárias encontradas durante os testes e não encerre apenas com um plano.
