# Cadastro de unidades — implementação local

## Comportamento

Administrador da empresa / Gestor de RH (perfil técnico administrador) recebe
a opção Unidades no menu. Nome da unidade, código, fuso horário e primeira
equipe são informados no cadastro; empresa vem exclusivamente da autenticação.
Padrões: America/Sao_Paulo e equipe Geral, editáveis antes de salvar.

Nome da unidade/equipe pode conter números. Código é convertido para maiúsculas,
com até 40 letras ASCII, números, hífen ou sublinhado. Nomes têm limite de 160
caracteres. Erros são mostrados junto aos campos pelo componente compartilhado
validacaoCadastro. Não altera as regras de nomes pessoais.

Unidade ativa, equipe ativa e dois eventos de auditoria são criados em uma
transação. Criação começa com marcação mobile desabilitada e localização vazia.
Não há edição, exclusão ou transferência nesta entrega.

## Interfaces

- GET /admin/unidades: página restrita ao administrador da empresa.
- GET /api/admin/unidades: lista unidades da empresa autenticada em unidades.
- POST /api/admin/unidades: campos nome, codigo, timezone, equipe_nome;
  resposta 201 com unidade e equipe. Empresa e campos desconhecidos são rejeitados.
- Falhas de validação: 400 com erro e campos; duplicidade: 409 com indicação
  do campo; falha transacional: rollback e mensagem sem detalhes internos.

/listar_unidades e /listar_equipes preservam seus contratos. Nova unidade e
equipe são compatíveis com as consultas existentes de cadastro de funcionários.
O link Configurar endereço abre /configuracoes?unidade=UUID#geofence-card;
somente IDs presentes na lista autorizada são selecionados. ID externo ou
inexistente deixa a seleção vazia e mostra aviso, sem consultar sua localização.

## Evidências locais

- Unidades: 9/9 testes de autenticação, RBAC, isolamento, payload, erros,
  transação e fechamento de conexão.
- PostgreSQL sintético 17: 5/5 testes com DDL das tabelas relevantes das
  migrations 002, 009 e 020; sem dados ou configurações privadas.
- Listagem existente: 3/3; localização mobile: 5/5.
- PostgreSQL confirmou unicidade de nome/código na empresa, mesmo código
  permitido em outra empresa, equipe visível na consulta existente e mobile
  desabilitado. Falhas de equipe ou segunda auditoria não deixam unidade parcial.
- Navegador: validação obrigatória, criação com nomes numéricos e equipe
  editada, código normalizado, duplicidade, link selecionando a unidade correta,
  aviso para unidade externa e layout em 390x844 com tema escuro.

Banco de testes criado em container local sem rede externa ou portas publicadas.
Runner compartilhou somente o namespace isolado do banco e recebeu montagens
somente leitura de código/DDL selecionados. Nenhum .env ou segredo montado.
Teste PostgreSQL exige UNITS_SYNTHETIC_TEST=1 e execução em container, cria
banco sintético novo por execução e não restaura backups. Container do banco
frequenia-units-synthetic-20261122 confirmado exited; dados sintéticos preservados.

Prévia em http://127.0.0.1:5184/admin/unidades usa fixtures em memória;
cadastros da prévia não são gravados no banco real.

## Limites e publicação

Sem migration, commit, push ou publicação nesta etapa. Mudanças preexistentes
preservadas. Nenhuma chamada AWS, leitura de dados pessoais ou alteração do
Supabase atual. Publicação posterior deve incluir o blueprint e seu registro
no app, serviço, template, assets, dependências compartilhadas de validação,
menu e integração nas configurações, com as confirmações do AGENTS.md.
