# FrequenIA — Resumo consolidado da implementação

Atualizado em: 12 de setembro de 2026  
Branch consolidada: `desenvolvimento-mvp`  
Repositório oficial: `https://github.com/frequenia/FrequenIA`

## Visão geral

O MVP possui backend Flask em Docker, banco Supabase/PostgreSQL, frontend web
administrativo e aplicativo Flutter. A identidade facial nova é vinculada a
`funcionario_id`, o reconhecimento é estritamente 1:1 e não existe busca facial
global.

## Backend e infraestrutura

- Python 3.10 e Flask executados com Gunicorn.
- Docker com 1 worker e 1 thread para previsibilidade de memória.
- `GET /health` técnico e `GET /status` funcional.
- Configuração oficial por `.env` em runtime; `.env.example` usa placeholders.
- Segredos não entram no Git nem na imagem Docker.
- CORS configurável e debug limitado ao desenvolvimento.
- Documentação de execução em `CONFIGURACAO_LOCAL.md`.

## Autenticação e autorização

- Login com JWT access token e claim `sid`.
- Refresh token rotativo e sessões persistentes em `auth_sessions`.
- Logout com revogação, sessões simultâneas e `/auth/me`.
- Recuperação de senha e primeiro acesso.
- RBAC centralizado, com distinção entre HTTP 401 e 403.
- Isolamento por `empresa_id` derivado da sessão.
- Perfil ou empresa enviados pelo cliente não são fonte de autoridade.

## Organização, usuários e perfil

- Novo schema para `usuarios`, `funcionarios`, `empresas`, `unidades`,
  `equipes` e `cargos`.
- Cadastro, edição e desativação administrativa de usuários.
- Migração controlada de usuários antigos sem criar senhas automáticas.
- `/perfil` usa o vínculo autenticado e os relacionamentos do novo schema.
- Senhas, tokens e outros dados sensíveis não são retornados.

## Jornadas e turnos

- Definições em `turnos` e períodos arbitrários em `periodos_turno`.
- Atribuições e histórico por vigência em `funcionarios_turnos`.
- Suporte a múltiplos períodos e `fim_dia_offset` para virada de dia.
- `GET /api/jornada` retorna a própria jornada.
- APIs e interface web administrativas permitem gerir turnos e atribuições.
- O fluxo novo não consulta a tabela legada `horarios`.

## Marcações e Controle de Ponto

- Registro oficial exclusivamente em `marcacoes`.
- Timestamp oficial produzido pelo PostgreSQL como `timestamptz`.
- Tipos semânticos: `entrada`, `saida_intervalo`, `retorno_intervalo` e
  `saida`.
- Marcações manuais e faciais preservam idempotência, advisory lock,
  concorrência e histórico imutável.
- A gestão consulta por `funcionario_id`, limitada à própria empresa.
- Controle de Ponto converte instantes apenas na apresentação para
  `America/Sao_Paulo`.
- Filtros de data respeitam o dia civil de São Paulo, inclusive próximo da
  meia-noite UTC.
- Tabela e exportações CSV, PDF e DOCX usam a mesma agregação de `marcacoes`.
- A primeira marcação confirmada de cada tipo no dia local é usada quando há
  duplicatas; nenhum registro é apagado.
- `/pontos` legado está desativado e não consulta a tabela `ponto`.

## Biometria e reconhecimento

- ArcFace com lazy loading thread-safe e reutilização da instância.
- Embeddings com 512 dimensões e normalização L2.
- Cadastro biométrico por `empresa_id` + `funcionario_id`.
- Histórico de biometria preservado por revogação.
- Cadastro com 3 a 5 imagens, média vetorial e uma única persistência final.
- Reconhecimento 1:1 por distância cosseno e threshold server-side.
- Liveness passivo MiniFASNet executado antes do ArcFace.
- Tentativas persistidas em `tentativas_faciais` sem imagem ou embedding.
- Tentativa `sucesso/match` pode autorizar uma única marcação facial dentro da
  janela server-side e fica vinculada por `marcacoes.tentativa_facial_id`.
- O fluxo web novo usa `biometrias`; a tabela `fotos` permanece apenas em
  código facial legado isolado.

## Flutter

- `BASE_URL` centralizada por `--dart-define`.
- Login, secure storage, restauração de sessão, refresh sincronizado e logout.
- Perfil e consulta da própria jornada.
- Câmera frontal e fluxo de ponto facial.
- Imagem enviada por multipart como JPEG, PNG ou WebP.
- Match gera tentativa temporária em memória e chamada de marcação facial com
  `Idempotency-Key`.
- Não match, liveness reprovado e biometria ausente não criam ponto.
- Foto não é salva na galeria nem persistida pelo aplicativo.
- O Flutter não acessa o Supabase diretamente e não contém segredos backend.

## Segurança preservada

- Identidade e empresa vêm da sessão autenticada.
- RBAC é aplicado no backend.
- Não há identificação por nome ou CPF no fluxo facial novo.
- Não há busca global de embeddings.
- Threshold e validade da tentativa não são controlados pelo cliente.
- Tokens, imagens, embeddings, CPF e secrets não devem aparecer em logs.
- Timestamps não são convertidos ou regravados no banco em horário local.

## Testes

Existem testes em `tests/` para autenticação, sessões, recuperação de senha,
RBAC, perfil, jornadas, marcações, arquitetura facial, biometria, reconhecimento
1:1, tentativas, liveness, marcação facial, média de embeddings e Controle de
Ponto. Os testes Flutter ficam em `mobile/test/`.

## Execução local resumida

```powershell
Copy-Item .env.example .env
docker build --tag frequenia-backend:local .
docker run --detach --name frequenia-backend-local --env-file .env --env PORT=5000 --publish 5000:5000 frequenia-backend:local
```

```powershell
cd mobile
flutter pub get
flutter run --dart-define=APP_ENV=development --dart-define=BASE_URL=http://10.0.2.2:5000
```

## Estado do Git

- Branch principal de desenvolvimento: `desenvolvimento-mvp`.
- Remotos `origin` e `frequenia` apontam para `frequenia/FrequenIA`.
- Nenhum remote desta cópia aponta para WorkSync.
- As branches antigas foram preservadas como histórico de segurança.

## Pendências futuras

- Calibração controlada do threshold ArcFace e do MiniFASNet.
- Avaliação de desafio ativo de liveness.
- UI mobile de primeiro acesso e recuperação de senha, se exigida pelo piloto.
- Ocorrências, correções, relatórios e regras trabalhistas em fases próprias.
- RLS, nuvem, CI/CD e observabilidade.
- Revisão de privacidade e conformidade antes do uso de biometria real.
