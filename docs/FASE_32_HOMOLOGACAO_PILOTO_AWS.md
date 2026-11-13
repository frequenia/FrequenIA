# Fase 32 — Homologação do piloto AWS existente

Data da inspeção: 2026-10-20 a 2026-10-21 (America/Sao_Paulo)

## Estado

Homologação externa **não concluída**. As validações locais, o inventário remoto
e uma sessão controlada do piloto foram executados sem acesso a produção ou uso
de dados reais. HTTPS e readiness passaram, e a presença dos endpoints das
Fases 30 e 31 foi comprovada. A correspondência criptográfica da imagem ativa,
o banco exclusivo de homologação, a migration remota e os fluxos autenticados
permanecem pendentes.

Nenhum recurso AWS foi criado, excluído ou reprovisionado. A única mutação foi
a abertura e o encerramento da sessão temporária pelo controlador existente.
Não houve commit, push, merge ou PR.

## Identidade, regiões e acesso observado

- conta mascarada: `********8156`;
- Console AWS já aberto no navegador: principal visível
  `frequenia-publisher`, região `sa-east-1`, no bucket de artefatos do piloto;
- AWS CLI: `2.37.9`, acima do mínimo `2.32.0`;
- perfis locais existentes: `default`, `frequenia-new` e
  `frequenia-pilot-publish`;
- após autorização específica, `aws login --profile
  frequenia-pilot-publish` substituiu a associação local expirada de `root`
  pelo usuário `frequenia-publisher`;
- STS confirmou a conta mascarada `********8156` e o ARN de usuário
  `frequenia-publisher`; nenhuma chamada foi feita com root;
- regiões consultadas: `sa-east-1` (runtime) e `us-east-1` (billing).

O usuário de publicação consegue descrever stacks somente por nome exato, mas
não possui listagem global de CloudFormation,
`ssm:DescribeInstanceInformation`, `ssm:ListCommands`,
`ssm:ListCommandInvocations`, leitura de SQS/DynamoDB/Lambda/CloudWatch nem
leitura das configurações globais do bucket. Essas negativas foram preservadas
como limites de evidência; nenhuma permissão foi ampliada.

O controlador efetivamente usado foi
`infra/aws/scripts/pilot-session.ps1`, com `start`, `status` e `stop`. A sessão
AWS no Chrome foi apenas lida; upload, exclusão e alterações não foram
acionados pelo navegador.

## Checkout e fingerprint local

- branch: `codex/aws-pilot-testing`;
- HEAD: `e1cd6fed1232c0e32f62920d938cd1ae18da5d95`;
- descrição: `e1cd6fe`;
- último commit: `2026-10-17T16:24:15-03:00`;
- arquivos rastreados modificados: nenhum;
- `git status --short` inicial: 31 entradas não rastreadas, todas preexistentes
  e preservadas; este relatório foi o único arquivo acrescentado pela sessão;
- `git ls-files -o --exclude-standard`: 50 arquivos não rastreados;
- fingerprint SHA-256 dos 148 arquivos rastreados copiados para `/app` pelo
  `Dockerfile.arm64`: `efa17a2c0b0c30746dec759b62a0413d987189050dcdfa97135e646cfb9ebc17`.

O contexto atual produziria 175 arquivos em `/app`: 148 rastreados e 27 PNGs
não rastreados em `static/img/brand/`. Como `Dockerfile.arm64` copia toda a pasta
`static`, esses arquivos preexistentes seriam incorporados em um rebuild.
Nenhuma nova imagem deve ser construída sem uma decisão explícita sobre esses
27 arquivos; eles não foram removidos nem alterados.

`.dockerignore` exclui `.env`, `.env.*`, `.secrets`, credenciais, chaves,
caches Python, testes, mobile, `output`, `document-assets`, `infra`, temporários,
fotos, dumps, backups, APKs e arquivos tar. A imagem ARM64 usa cópias explícitas
da aplicação, migrations e comandos de dispatcher/worker.

## Artefatos locais e correspondência

| Artefato | SHA-256 do arquivo | Digest/config da imagem | Arquitetura |
|---|---|---|---|
| `frequenia-arm64-pilot-candidate-20261016.tar.gz` | `67ab2cd1481b85eb325a4aac45e4410489fd13a029f80d0cd943bf1d04e30619` | `sha256:67fcf356c67fe52885f051de195b85ce21670dd414f76f5be04a409cf337e89a` | ARM64 |
| `frequenia-arm64-pilot-candidate-20261017.tar.gz` | `e40602cfefe4a8cb7479206d89286cc0b3106d4637ade9dabdc609869b301cf9` | `sha256:7e395b0c9d07f8a550946038a83c32a5ac0d8030efb9d78f00c3d7a9101695fa` | ARM64 |
| `frequenia-arm64.tar.gz` | `53993a17ec72c11d0e61367a7fc4e29de763b4d973424fdc85ed473fcf91bda3` | não reinspecionado | candidato legado de 14/10 |

A candidata de 17/10 contém 175 caminhos em `/app`, sem caminho ausente ou
extra em relação ao checkout atual. A comparação SHA-256 por arquivo encontrou
três divergências reais:

- `routes/journeys.py`;
- `services/daily_journey.py`;
- `services/journey_observability.py`.

Portanto, a candidata de 17/10 **não corresponde byte a byte ao HEAD atual**.

O inventário S3 de 20/10 confirmou:

- ponteiro `runtime/current-image-key.txt`, 96 bytes, atualizado em
  `2026-10-19T18:31:56Z`;
- chave apontada: `runtime/frequenia-arm64-be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa.tar.gz`;
- objeto imutável: 919.741.243 bytes, atualizado em
  `2026-10-19T14:09:12Z`, SSE-S3/AES256;
- SHA-256 declarado no nome e nos metadados do objeto:
  `be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa`;
- chave legada `runtime/frequenia-arm64.tar.gz`: 926.284.294 bytes,
  atualizada em `2026-10-14T20:54:56Z`.

O SHA remoto foi confirmado como metadado, mas o objeto de aproximadamente
920 MB não foi transferido integralmente nesta inspeção. Ele não coincide com
nenhum dos três SHA-256 dos arquivos locais listados acima. A correspondência
entre o objeto remoto, o HEAD e o digest carregado na EC2 permanece **não
comprovada**. Durante a sessão de 21/10, a aplicação ativa expôs rotas que só
existem após as Fases 30 e 31, o que exclui operacionalmente a imagem legada de
14/10, mas não substitui uma inspeção do digest Docker.

## Automação de boot e stacks

O template local `infra/aws/runtime.template.yaml` não consulta
`runtime/current-image-key.txt`. O `UserData` grava
`ARCHIVE_KEY='${ContainerArchiveKey}'`, baixa essa chave diretamente em todo
boot e executa `docker load`. Assim, uma stack que continue com
`ContainerArchiveKey=runtime/frequenia-arm64.tar.gz` continuará carregando a
chave legada, salvo se o script efetivamente instalado na EC2 tiver sido
alterado fora deste template.

O S3 também contém um boot imutável publicado em 19/10,
`runtime/frequenia-boot-01ae11aa2408a2a4b593d3e37220a2680d33e935388dfd6332a30bb63de534bd.sh`.
Esse script fixa diretamente a imagem imutável `be1d…6aa`, baixa e carrega a
imagem em todo boot, e inicia Gunicorn, dispatcher, worker, ClamAV e Caddy em
contêineres separados. O readiness exige `/ready`, dispatcher e worker ativos.

Há ainda `runtime/instalar-automacao-ec2.sh`, atualizado em 19/10, que faz
backup do boot instalado e o altera para consultar
`runtime/current-image-key.txt` na próxima inicialização. A existência desse
instalador no S3 **não comprova sua execução na EC2**. A política do usuário
negou leitura do `UserData` e do histórico SSM, portanto somente uma inspeção
controlada da instância poderá distinguir entre o boot fixado em `be1d…6aa`, o
boot que resolve o ponteiro e uma versão anterior.

A EC2 `i-0b05f77cae35912f8` foi confirmada como `t4g.small`, ARM64,
`sa-east-1a`, com IMDSv2 obrigatório. A sessão controlada iniciou a instância em
`2026-10-21T14:20:01Z` e o controlador a encerrou em
`2026-10-21T14:29:41Z`. O estado final comprovado é `stopped`.

Stacks verificadas por nome exato:

- `frequenia-pilot-runtime`: `CREATE_COMPLETE`, sem update desde 14/10,
  `ContainerArchiveKey=runtime/frequenia-arm64.tar.gz`;
- `frequenia-pilot-attachments`: `UPDATE_COMPLETE`, atualizada em 19/10, com
  bucket privado, SQS e DLQ existentes;
- `frequenia-pilot-artifacts-sa` e `frequenia-pilot-budget`:
  `CREATE_COMPLETE`.

O template original implantado usa `ContainerArchiveKey`, não contém o
ponteiro, dispatcher/worker separados, SQS explícita nem
`BIOMETRIC_AWAY_POLICY`. Portanto a configuração observada no runtime foi
instalada operacionalmente fora do template original. Nenhum change set foi
criado.

## Migrations e ensaio descartável

- migrations presentes: sequência contínua `001`–`026`;
- última migration: `026_biometric_governance_lifecycle.sql`;
- PostgreSQL/pgvector local descartável: usado com fixtures sintéticas;
- Fase 31: instalação limpa e upgrade representativo `001–025 → 026`
  passaram, preservando biometria legada conforme o contrato;
- Fase 29: `pg_dump`, manifesto, restauração isolada e conferência de dados
  passaram usando o cliente do próprio contêiner descartável;
- contêineres temporários PostgreSQL, Moto e ClamAV foram removidos ao final.

Isso não comprova o banco AWS/Supabase de homologação. TLS, identidade do
branch/projeto, backup recuperável e restore remoto ainda precisam ser
confirmados sem ler ou exibir `DATABASE_URL`.

### Continuação da barreira do banco em 21/10/2026

Foram repetidas apenas verificações sem escrita antes de qualquer login,
fixture ou migration:

- o checkout continua em `codex/aws-pilot-testing`, HEAD
  `e1cd6fed1232c0e32f62920d938cd1ae18da5d95`, com todas as alterações
  preexistentes preservadas;
- não existe vínculo local do Supabase CLI, arquivo `project-ref`, variável de
  ambiente local com nome relacionado a banco/Supabase/homologação ou aba já
  aberta do dashboard Supabase;
- o repositório não contém identificação não secreta do projeto/branch usado
  pelo piloto nem registro de backup/restore desse destino; as evidências das
  Fases 28/29 são explicitamente locais e descartáveis;
- `db.py` força `sslmode="require"` e `connect_timeout=15` em toda conexão.
  Isso comprova o requisito TLS do cliente presente na fonte, mas não identifica
  o host/branch efetivamente configurado nem comprova a negociação da conexão
  ativa;
- a tentativa de obter metadados do SecureString via `ssm get-parameter` foi
  bloqueada antes da execução porque a API também recuperaria o campo de valor.
  Nenhum SecureString ou `DATABASE_URL` foi lido;
- STS reconfirmou o usuário restrito `frequenia-publisher` na conta mascarada
  `********8156`; a EC2 foi reconfirmada em `stopped`, sem IP público.

A barreira permanece **não superada**. Faltam, cumulativamente:

1. identificador não secreto e mascarável do projeto e branch exclusivos de
   homologação;
2. atestação, sem revelar URL/credenciais, de que o parâmetro ativo do piloto
   referencia exatamente esse projeto/branch;
3. evidência da política/estado de backup desse branch e de uma restauração
   verificada em clone/destino isolado, com data e resultado;
4. evidência operacional de TLS do destino ativo, além da configuração
   `sslmode=require` da fonte.

Por essa razão não foram criadas sessões autenticadas, não foi consultado o
schema remoto, não foi aplicada a migration `026` e nenhum fluxo com escrita no
banco foi executado nesta continuação.

## Validações realmente executadas em 20/10/2026

| Validação | Resultado |
|---|---|
| descoberta backend | 352 testes: 255 sucessos, 97 skips opt-in explícitos, 0 falhas |
| controles de custo AWS | 7/7 |
| Fase 25 PostgreSQL | 31/31 |
| Fase 26 PostgreSQL/anexos | 17/17 |
| Fase 27 PostgreSQL/Moto S3/ClamAV EICAR | 8/8 |
| Fase 28 PostgreSQL/Moto SQS | 9/9 |
| Fase 29 continuidade/dump/restore | 7/7 após configurar o cliente descartável previsto |
| Fase 30 jornada/concorrência | 12/12 |
| Fase 31 governança/upgrade/concorrência | 13/13 |
| Flutter analyze `--no-pub` | sem issues, 161,4 s |
| Flutter test `--no-pub` | 48/48 |
| `cfn-lint` nos quatro templates | 0 erros; 4 avisos W3002 esperados para diretórios Lambda empacotados pelo pipeline |
| GitHub Actions para o HEAD | nenhum run de pull request associado ao commit foi retornado |

O ClamAV descartável atualizou `daily.cld` para a versão 28159 antes da suíte.
Os resultados locais não são SLO, precisão biométrica, conformidade LGPD nem
prova de operação do piloto AWS.

## APK

O Console AWS mostrou no prefixo `apk/`:

- `frequenia-1.0.0-pilot.1.apk`, 51,9 MB, modificado em 14/10/2026 às
  22:09:07 -03;
- `frequenia-1.0.0-pilot.1.apk.sha256`, 95 bytes, modificado em 14/10/2026;
- `frequenia-latest.apk`, 51,9 MB, modificado em 14/10/2026.

O APK foi baixado temporariamente e validado:

- SHA-256 publicado e recalculado:
  `a2058888df865c2f2d8d4eb62673c7408eacc711d9769b1778b882034a6abbb5`;
- pacote `br.com.frequenia.app`, `versionName=1.0.0`, `versionCode=1`,
  `minSdk=26`, `targetSdk=36`;
- assinatura APK v2 válida, um signatário, certificado `Android Debug`,
  fingerprint SHA-256
  `71ad3013ed4c81831a83a0bad6532d19c6104a23388e42a5697fc58772354823`.

A fonte atual declara `1.0.0+1`, mas recebeu dois commits que alteram `mobile/`
em 17/10, posteriores ao APK. O APK está, portanto, **defasado em relação ao
HEAD escolhido**. A tentativa de preparar localmente um candidato com código
de versão 2 foi interrompida porque a ferramenta Flutter bloqueou antes mesmo
de responder a `flutter --version`; não houve alteração de fonte nem artefato
novo validado. Nada foi publicado em bucket ou loja.

## Testes externos e segurança

Resultados obtidos na sessão de 21/10:

- DNS `frequenia.duckdns.org` atualizado para o IP temporário da EC2;
- HTTPS válido, servido por Caddy, com Gunicorn respondendo;
- `/health`: HTTP 200;
- `/ready`: inicialmente HTTP 503 somente com `signatures=false`; após a
  atualização do ClamAV, HTTP 200 com `storage`, `queue`, `scanner` e
  `signatures` todos `true`;
- a porta 443 reiniciou brevemente durante a atualização e estabilizou antes da
  homologação de readiness;
- endpoints `/api/marcacoes/proxima`,
  `/api/admin/governanca-biometrica/readiness` e `/api/biometria/estado`
  existem e retornaram 401 sem autenticação, comprovando a presença das Fases
  30 e 31 e a barreira de RBAC;
- dois caminhos de ocorrência com UUIDs sintéticos distintos retornaram o
  mesmo 401 antes de lookup, sem enumeração anônima.

Permanecem pendentes: digest efetivo do container, supervisão interna de
dispatcher/worker, DLQ e alarmes, autenticação/RBAC/tenant com usuários
sintéticos, jornada/timezone/concorrência, Gestor → RH, visão efetiva, anexos,
geofence, biometria 1:1 e seus estados, desligamento, hold, eliminação e
independência de `falha_facial`.

Os testes autenticados não foram iniciados porque criariam sessões no banco e
não foi possível provar, sem acessar segredo, que o `DATABASE_URL` aponta para
branch exclusivo de homologação com TLS, backup e restore verificável. Essa
barreira também bloqueou a verificação/aplicação da migration `026`.

Não foram consultados valores de `.env`, `.secrets`, SSM SecureString, token
DuckDNS, `DATABASE_URL`, JWT, Flask ou chave de assinatura. Não houve acesso a
produção, PII, fotos, embeddings, usuários ou marcações reais.

## Rollback, custos e encerramento

O rollback operacional da sessão foi executado pelo controlador existente:
`stop` expirou o prazo, solicitou o desligamento e a EC2 foi confirmada em
`stopped`. Uma eventual publicação deve preservar o artefato anterior, usar chave imutável,
revisar change set sem replacement da EC2, restaurar a aplicação anterior em
falha de readiness e restaurar somente o clone de homologação em falha de
migration. Schema não deve ser revertido automaticamente.

Permanecem custos residuais potenciais dos recursos já existentes: EBS, S3,
DynamoDB, SQS, SNS, CloudWatch e Budgets. A sessão consumiu aproximadamente dez
minutos; o controlador informou `cost_lock=false`, uso mensal de 35.571 s antes
da sessão e limite de 144.000 s. A EC2 foi confirmada remotamente em `stopped`
ao final.

## Decisões pendentes

- base legal e referência documental;
- retenção e condições de hold;
- conteúdo, responsável e canal do aviso;
- política de afastamento para uso real;
- dataset/protocolo de calibração;
- RPO/RTO corporativos;
- decisão sobre os 27 PNGs de marca não rastreados antes de qualquer rebuild;
- acesso/evidência suficiente para confirmar banco exclusivo de homologação,
  TLS, backup e restauração antes de qualquer migration remota;
- reconstrução e validação do APK defasado antes de qualquer publicação.

Em 25/10/2026, a reconstrução release foi preparada como `1.0.1+2`, com chave
própria do piloto (RSA 4096, fora do Git), assinatura APK v2 válida e SHA-256
`9571378fa548d25d05faa3a49573486d3481c264a2d2b6479698c1140013e6a8`.
Análise Flutter e 48 testes passaram. Como o APK anterior usa certificado
Android Debug, a primeira instalação desta versão release exige desinstalar a
versão antiga; versões release futuras poderão atualizar normalmente se a
mesma chave for preservada. O upload ainda depende de confirmação específica.

O upload foi autorizado e concluído em 25/10/2026: versão imutável
`1.0.1-pilot.2`, checksum e ponteiro público `frequenia-latest.apk`. O script
retornou o mesmo SHA-256 validado localmente. A versão `1.0.0-pilot.1` segue
preservada para rollback. Uma segunda leitura integral do objeto público ficou
pendente por limite do revisor de permissões, sem impacto sobre o upload.

## Evidência adicional do painel Supabase — 22/10/2026

Fonte: painel Supabase já autenticado pela usuária, inspecionado com autorização
específica em modo somente leitura em 22/10/2026. Responsável pela apresentação
e pelas atestações: usuária, operadora da configuração do piloto AWS. A tela
`Connect`, URLs de conexão, senhas, tokens, chaves e valores de SecureString não
foram abertos ou consultados.

### Observado diretamente no painel

- organização exibida: `frequenia-homologacao`;
- projeto: `frequenia's Project`;
- Project ID/Reference ID, registrado somente de forma mascarada:
  `xoof…esgx`;
- região: `sa-east-1` — South America (São Paulo);
- branch selecionada: `main`;
- plano: Free, conforme aviso da área de backups;
- `Database Settings > SSL configuration`: opção `Enforce SSL on incoming
  connections` desligada;
- `Database > Backups > Scheduled backups`: aviso explícito de que o plano
  Free não inclui backups do projeto;
- `Database > Backups > Restore to new project`: recurso exige plano Pro ou
  superior e backups físicos habilitados.

Essas telas comprovam a identidade não secreta do projeto selecionado e o
estado das configurações exibidas, mas não comprovam o conteúdo do banco nem a
configuração efetivamente carregada pela EC2. A branch `main` observada não foi
presumida como branch separada de homologação. Nenhuma configuração foi
alterada e nenhum botão de restore, upgrade, SSL, branch ou projeto foi
acionado.

### Atestado pela operadora

Em 22/10/2026, a usuária, responsável pela configuração da AWS, declarou que:

- a configuração do piloto aponta para `xoof…esgx/main` e esse é o banco do
  piloto;
- os dados do banco do piloto são fictícios;
- o projeto Supabase é usado exclusivamente para testes do FrequenIA, sem outro
  uso real.

São atestações da operadora, não verificações independentes. Nenhuma
configuração AWS, URL de conexão, segredo, schema ou linha do banco foi
consultada neste passo. A declaração estabelece o vínculo informado, mas não
comprova a configuração efetivamente carregada pelo runtime nem valida de forma
independente a exclusividade e a natureza sintética dos dados.

### Não comprovado

- TLS efetivo da conexão ativa: SSL Enforcement desligado não impede uma
  conexão TLS, mas não a exige; `sslmode=require` no código não demonstra o
  modo negociado pela conexão ativa nem verifica a identidade do servidor;
- mecanismo de backup aplicável ao ambiente: o painel confirma que o plano
  Free não oferece backups programados;
- restauração datada e verificada em clone/destino isolado: não há registro e o
  recurso gerenciado observado exige plano Pro ou superior com backups físicos;
- correspondência independente entre o ambiente observado e a configuração
  efetivamente carregada pelo runtime do piloto.

Nenhuma alteração foi feita no projeto, branch, SSL, plano ou backup.

### Estado após a evidência de 22/10/2026

A Fase 32 permanece **parcialmente homologada**. Ainda faltam:

1. verificação não secreta de que a configuração **efetivamente carregada**
   pelo runtime do piloto corresponde ao vínculo `xoof…esgx/main` atestado
   pela usuária, sem expor URL de conexão ou credenciais;
2. validação independente, sem expor dados pessoais, das declarações da
   usuária de que o projeto é exclusivo para testes do FrequenIA e contém
   somente dados fictícios;
3. TLS efetivo habilitado e evidência de conexão negociada no destino correto;
4. mecanismo de backup aplicável e restauração verificada em destino isolado.

Enquanto qualquer item faltar, não serão executados migration `026`, schema
remoto, sessões autenticadas ou fluxos que escrevam no banco.

## Proposta para uma próxima autorização — não executada

Esta proposta foi preparada em 22/10/2026 a partir da inspeção acima e da
documentação oficial atual do Supabase. Não constitui autorização para alterar
o projeto, acessar AWS, criar destino, exportar dados, restaurar backup, aplicar
migration ou iniciar o piloto.

**Revisão posterior na mesma data:** a proposta abaixo pressupunha um banco
com dados exclusivamente sintéticos. A operadora depois confirmou embeddings
de pessoas reais da equipe e links para fotos no próprio `xoof…esgx/main`.
Portanto, a rota de copiar o backup inteiro para um segundo projeto **não está
aprovada**: ela também copiaria dados biométricos reais. O plano de ensaio
sintético e a sequência de liberação abaixo não devem ser executados como
estão. Preservar o projeto e os dados, conforme pedido da usuária, e elaborar
em tarefa separada um plano de tratamento/segregação e continuidade para dados
reais antes de qualquer exportação, clone ou teste autenticado.

### Decisão de continuidade

Em 22/10/2026, a usuária escolheu permanecer no plano Free e manter o projeto
existente `xoof…esgx/main` como ambiente de homologação do piloto. Não foi
proposta troca do banco ativo da AWS nem criação de branch permanente. Um
segundo projeto seria apenas destino isolado e temporário para comprovar o
restore do backup lógico do ambiente existente; nunca seria usado para
restaurar por cima do projeto ativo.

Em inspeção somente leitura do painel na mesma data, a organização exibiu dois
projetos cadastrados: o projeto do FrequenIA ativo e outro projeto preexistente
pausado, cujo nome e identificador não foram registrados por serem alheios a
esta homologação. A documentação oficial de cobrança informa que projetos
pausados não contam no limite de dois projetos Free ativos. Há, portanto, uma
vaga ativa provável para um novo destino Free isolado, sujeita à confirmação
da própria tela de criação no momento autorizado. O projeto pausado não será
reativado, reutilizado, alterado ou excluído para esta finalidade.

A rota escolhida ainda depende de verificação de limite disponível e de
autorizações específicas para cada mutação:

1. **Manter o plano Free e implantar continuidade manual**: confirmar se existe
   uma segunda vaga gratuita disponível, propor um novo projeto remoto isolado
   para homologação de restore, produzir backup lógico por operador autorizado,
   armazená-lo fora do projeto de origem com proteção definida e restaurá-lo no
   destino isolado. A aceitação exige registrar data, responsável, origem e
   destino mascarados, ferramenta/versão, contagens ou digests não sensíveis,
   resultado de integridade e descarte/retenção aprovados. Criar projeto,
   exportar, restaurar e eventualmente excluir o destino são mutações separadas
   e exigem autorização; não se deve usar um restore PostgreSQL local
   descartável como evidência suficiente do ambiente remoto.
2. **Alternativa não escolhida no momento — migrar a organização para Pro e
   usar backup físico gerenciado**: preço
   público consultado de **US$ 25/mês**, com um projeto Micro incluído via
   crédito de compute e backups diários retidos por sete dias. `Restore to a new
   project` exige plano pago e backup físico; o novo projeto independente cobra
   compute/disco próprios, apresentados antes da criação. Essa rota reduz a
   operação manual, mas introduz assinatura e custo adicional do clone. PITR
   não é necessário para a barreira atual e começa em aproximadamente
   **US$ 100/mês** para sete dias, além dos demais custos.

Fontes oficiais consultadas em 22/10/2026:

- [Database Backups](https://supabase.com/docs/guides/platform/backups);
- [Restore to a new project](https://supabase.com/docs/guides/platform/clone-project);
- [Pricing](https://supabase.com/pricing);
- [About billing](https://supabase.com/docs/guides/platform/billing-on-supabase).

Nenhum custo foi aceito. Os valores são referências públicas atuais e devem ser
reconfirmados na tela de cobrança antes de qualquer contratação ou criação.

### Proposta de TLS

O estado pretendido, ainda não aplicado, é cumulativo:

1. preparar cliente/runtime para `sslmode=verify-full`, com a CA oficial do
   Supabase incorporada por mecanismo controlado e sem colocar URL, senha ou
   certificado privado no Git;
2. validar primeiro em clone/destino isolado que a CA e o hostname são
   verificados e que a conexão negociada usa TLS;
3. em janela controlada, habilitar `Enforce SSL on incoming connections` no
   projeto correto; a documentação informa reinicialização breve do banco e
   possível indisponibilidade de alguns minutos;
4. verificar conexão efetiva e identidade do servidor no runtime do piloto,
   expondo no relatório somente resultado, data, operador e identificador
   mascarado;
5. rollback proposto: desabilitar o enforcement somente se a indisponibilidade
   decorrer da política, preservar a configuração anterior e encerrar a sessão
   do piloto. A mudança de cliente para `verify-full` deve ser revertida pela
   imagem anterior, não por exposição ou edição manual de segredos.

`sslmode=require` cifra a conexão, mas não verifica CA ou hostname. A referência
oficial recomenda `verify-full` quando SSL Enforcement está habilitado:
[Postgres SSL Enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement).

### Proposta de comprovação do vínculo com o runtime

Em sessão AWS futura e especificamente autorizada, o operador responsável deve
comparar privadamente a configuração efetivamente carregada pelo contêiner com
`xoof…esgx/main`. O assistente não deve receber nem imprimir a URL. A evidência
aceitável deve conter apenas: data, operador, instância/piloto mascarado, imagem
ou digest executado, resultado booleano de correspondência e Reference ID
mascarado. Ler o painel Supabase ou o parâmetro cadastrado, isoladamente, não
comprova o valor carregado pelo processo.

### Sequência proposta depois das quatro evidências

Somente após identidade exclusiva, vínculo, TLS efetivo e restore isolado
estarem comprovados:

1. autorização separada para ensaio `001–025 → 026` em clone remoto isolado,
   com dados exclusivamente sintéticos, backup confirmado e rollback do clone;
2. revisão do resultado e autorização separada para migration do banco de
   homologação, sem rollback automático de schema;
3. construção de imagem imutável a partir do checkout aprovado, decisão prévia
   sobre os 27 PNGs não rastreados e registro de SHA-256/digest;
4. change set sem replacement da EC2, publicação preservando a imagem anterior,
   sessão controlada do piloto e testes autenticados com dados sintéticos;
5. encerrar a sessão e confirmar `stopped` ao final;
6. reconhecimento facial somente após decisão formal do controlador/DPO sobre
   hipótese legal, necessidade/proporcionalidade, alternativa não punitiva,
   aviso/canal, retenção/hold, afastamento, incidentes, RIPD e protocolo de
   acurácia/equidade.

As Fases 33 e 34 continuam concluídas apenas localmente; esta proposta não
reclassifica a aprovação jurídica, a validação de relatórios ou a homologação
do piloto.

## Retomada documental em 22/10/2026 — sem nova operação remota

Fonte: revisão deste relatório e das páginas oficiais do Supabase sobre
[Reference ID](https://supabase.com/kb/troubleshooting/forbidden-resource-error-from-the-cli-L6rm6l),
[branches no painel](https://supabase.com/docs/guides/deployment/branching/dashboard),
[SSL Enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement) e
[backups](https://supabase.com/docs/guides/platform/backups), consultadas em
22/10/2026. Responsável pela revisão: assistente; as observações do painel e
as declarações da usuária continuam atribuídas às fontes indicadas acima.
Até a autorização de inspeção descrita a seguir, não houve nova consulta ao
painel, runtime ou banco nesta retomada.

Após autorização específica da usuária, houve nova inspeção **somente leitura**
do painel no mesmo dia. Em `Project Settings > General`, foram reconfirmados
nome `frequenia's Project`, Reference ID mascarado `xoof…esgx`, região
`sa-east-1`, organização `frequenia-homologacao`, plano Free e uma integrante
com papel Owner (identidade pessoal omitida). O cabeçalho mostrava `main`
rotulada `PRODUCTION`, e a visão geral indicava `No branches`; isso não prova
isolamento por branch. Em `Database > Settings`, o controle `Enforce SSL on
incoming connections` estava desligado. Em `Database > Backups > Scheduled
backups`, o painel informou que o plano Free não inclui backups do projeto.
Nenhum controle foi alterado, nenhuma tela `Connect` ou chave foi aberta, e
nenhum conteúdo ou schema do banco foi consultado. Responsável pela inspeção:
assistente, na sessão autenticada pela própria usuária em 22/10/2026.

Na continuação de 22/10/2026, a usuária respondeu que ela própria administra
o banco e a configuração do piloto. Fonte: declaração direta da usuária nesta
tarefa; responsabilidade declarada, não verificação independente do vínculo
ativo, do TLS ou de restauração isolada.

Questionada se já havia restaurado um backup desse projeto em outro banco
separado e conferido o resultado, a responsável respondeu **“não”** em
22/10/2026. Trata-se de declaração da operadora, não de inspeção de backup.
Portanto, não há registro de restauração isolada verificada para apresentar.
O próximo passo, em tarefa e autorização separadas, é propor alvo isolado,
custo/limites do plano Free, efeitos, proteção do backup, conferência de
integridade e rollback antes de qualquer exportação ou restore. Nunca restaurar
por cima de `xoof…esgx/main`.

Na mesma data, a usuária esclareceu que as imagens reservadas para testes são
de pessoas reais da própria equipe e expressou intenção de guardá-las para
eventual treinamento futuro. Não foram fornecidas imagens nem foi verificado
onde estão armazenadas ou se alguma já foi enviada ao piloto. Essa declaração
impede tratar a afirmação anterior de “somente dados sintéticos” como prova
suficiente para os testes faciais. Antes de qualquer sessão autenticada ou
consulta remota, a operadora deve confirmar **sem mostrar fotos nem dados** se
essas imagens/biometrias reais chegaram ao FrequenIA ou permanecem fora dele.
Se já houver dados reais no projeto, a premissa de homologação exclusivamente
sintética não se sustenta e a barreira permanece fechada até nova avaliação
específica do controlador/DPO. Nada foi consultado ou apagado neste passo.

Em resposta à pergunta sobre o local das fotos, a usuária declarou em
22/10/2026: **“estão guardadas no bd do supabase”**. O assistente não verificou
o banco, o projeto exato, a tabela ou o conteúdo; não solicitou nem viu as
imagens. Assim, a declaração anterior de banco do piloto com dados somente
fictícios está **em conflito com a nova informação** e não pode sustentar a
homologação. Até que a controladora identifique privadamente o destino e
avalie o tratamento dos dados reais com o responsável jurídico/DPO, não
consultar schema ou dados, não aplicar migration `026`, não executar testes
autenticados nem publicar/ativar o reconhecimento facial. Preservar os dados
existentes sem apagamento automático; eventual retenção, restrição de acesso
ou eliminação exigem decisão específica da controladora.

Em esclarecimento posterior na mesma data, a usuária especificou:
**“embeddings e link das fotos”**. Isso corrige a interpretação de que os
arquivos originais estejam necessariamente em uma tabela do banco. Segundo a
declaração, há embeddings vinculados à equipe e referências às fotos no
Supabase; o local dos arquivos apontados, o projeto exato e as condições de
acesso/retenção não foram verificados. Não abrir os links. Mesmo sem fotos
binárias em tabela, embeddings identificáveis de pessoas reais não satisfazem
a premissa de dados exclusivamente sintéticos.

A usuária esclareceu ainda que deseja conservar os dados da equipe agora e,
futuramente, os de funcionários reais da empresa para melhorar o
reconhecimento. Esta é uma **finalidade futura proposta**, não evidência de
autorização de uso para treinamento, nem confirmação de que dados de
funcionários já estejam no banco. Não misturar ensaios de homologação com
cadastros reais. Antes de qualquer coleta ou treinamento com funcionários,
definir separadamente base jurídica para biometria sensível, aviso, alternativa,
necessidade, prazo de retenção, acesso, eliminação, avaliação de impacto e
validação técnica; nenhum prazo indefinido foi aprovado nesta retomada.

Por fim, a usuária confirmou em 22/10/2026 que os embeddings da equipe e os
links das fotos estão no **mesmo projeto Supabase do FrequenIA** usado pelo
piloto, identificado no painel como `xoof…esgx/main`. Fonte: declaração direta
da operadora; os registros e links não foram abertos nem verificados pelo
assistente. A identidade do projeto agora está atestada pela responsável,
mas a exclusividade **sintética** exigida para esta homologação não se sustenta
com a presença declarada de biometria de pessoas reais. Isso bloqueia a
reclassificação da Fase 32 e qualquer teste autenticado/migration nesta tarefa.
Não apagar ou mover os dados por inferência; a controladora precisa decidir o
tratamento e a segregação em trabalho posterior, com avaliação de privacidade
e autorização específica para qualquer mutação.

Na sequência, a usuária pediu expressamente **não apagar os dados**, continuar
usando-os para testes e liberar o reconhecimento facial o quanto antes. Nenhum
dado foi apagado ou alterado. O pedido de prioridade não supre as evidências
pendentes de vínculo ativo, TLS e continuidade nem a avaliação de tratamento
biométrico de pessoas reais. Esta retomada documental não executa publicação,
migration ou teste autenticado; a ativação exige decisão e autorização próprias
em etapa posterior.

Inspeção **somente local** do código em 22/10/2026: a rota atual de cadastro
(`routes/biometrics.py`) processa imagens para gerar o embedding e insere
`referencia_arquivo_privado=NULL`; a migration `005` permite essa referência,
mas não obriga preenchimento. A migration `026` prevê eliminá-la junto com o
embedding no ciclo de retenção. Portanto, o código local atual **não comprova**
que links de fotos sejam gravados pelo fluxo vigente. A declaração da usuária
sobre links no Supabase pode refletir dados legados, outra rotina ou outra
referência; não foi feita inspeção remota para distinguir essas hipóteses.
Nenhum valor de URL, imagem ou embedding foi lido.

Ao ser perguntada sobre os titulares já cadastrados, a usuária esclareceu em
22/10/2026 que são **somente desenvolvedores do sistema**. Fonte: declaração
da operadora; vínculo empregatício/contratual, ciência dos participantes e
base jurídica não foram comprovados. Isso distingue o ensaio técnico atual
da intenção futura de cadastrar funcionários da empresa, mas não torna os
embeddings dos desenvolvedores dados sintéticos nem autoriza treinamento.

Ao ser perguntada sobre aviso prévio e possibilidade de recusa, a operadora
respondeu inicialmente “não”, mas **corrigiu expressamente** em 22/10/2026:
**“foi avisado, respondi errado”**. Assim, o estado atualizado é aviso aos
desenvolvedores **declarado pela operadora**, não ausência de aviso. O conteúdo,
a data, a forma do aviso, a informação sobre treinamento futuro e a liberdade
de recusa ainda não foram comprovados. A correção não fornece, por si só,
referência da hipótese jurídica aplicável nem prazo aprovado de retenção.
Preservar os dados conforme instrução da usuária, sem apagamento, consulta ou
compartilhamento nesta tarefa; definir as demais condições em etapa autorizada.

Em esclarecimento adicional na mesma data, a operadora declarou que a
participação dos desenvolvedores nos testes faciais foi **voluntária**, com
possibilidade de recusa sem prejuízo. Fonte: declaração direta, sem acesso a
termos, mensagens ou dados dos participantes. Essa informação não equivale à
aprovação automática da hipótese legal para biometria sensível, não abrange
treinamento futuro e não elimina as pendências técnicas da Fase 32.

A operadora decidiu expressamente em 22/10/2026 limitar o piloto pretendido
a **reconhecimento facial 1:1 com desenvolvedores voluntários**. O uso de
embeddings para treinamento de IA **não entra nesse piloto** e permanece
finalidade futura separada, sem autorização de tratamento nesta etapa.
Essa delimitação não comprova por si só a hipótese jurídica, a versão do aviso,
o prazo de retenção, o vínculo do runtime, TLS ou continuidade.

Ao perguntar como a concordância dos desenvolvedores foi registrada, a
operadora respondeu **“Houve apenas aviso verbal”** em 22/10/2026. Não foi
apresentado termo ou mensagem de adesão específica ao teste biométrico 1:1.
Antes de novos testes com pessoas reais, preparar informação escrita correta
sobre finalidade, dados, local, acesso, duração, direitos, alternativa e
contato, e registrar a escolha livre de cada participante após revisão da
hipótese jurídica aplicável. Um registro novo não deve ser descrito como
validação retroativa da coleta anterior. Nenhuma comunicação foi enviada aos
participantes nesta tarefa.

A operadora indicou `frequenia@gmail.com` como e-mail de contato proposto para
o piloto inicial e disse que este será usado “por um tempo”. Em resposta
posterior, em 22/10/2026, escolheu uma **janela planejada de 60 dias de testes
com revisão antes da continuidade**, limitada aos desenvolvedores voluntários
e ao reconhecimento facial 1:1, sem treinamento de IA. Fonte: declaração
direta da operadora; a data efetiva de início, a revisão e o funcionamento do
canal ainda não foram comprovados. Esses 60 dias **não** são prazo aprovado de
guarda dos embeddings ou links de fotos, não autorizam retenção indefinida e
não configuram exclusão automática. Nenhum dado foi apagado ou alterado.

Em 22/10/2026, ao pedir a publicação para testar, a operadora esclareceu que
pretende usar fotos reais suas e de mais uma pessoa, a qual declarou já ter
aceitado participar. Fonte: declaração da operadora; identidade, conteúdo e
registro dessa aceitação não foram verificados. Essa autorização não transforma
os registros existentes em dados sintéticos e não autoriza, por si só, acesso
às fotos pelo assistente, alteração do banco ou uso para treinamento. Nenhuma
imagem ou embedding foi solicitado, recebido ou consultado nesta retomada.

| Evidência cumulativa | Situação documental |
|---|---|
| Ambiente exclusivo e dados sintéticos | `xoof…esgx/main`, organização `frequenia-homologacao` e plano Free observados no painel. A operadora confirmou que os embeddings reais da equipe e links para fotos estão nesse mesmo projeto; o conteúdo não foi inspecionado. O requisito de dados exclusivamente sintéticos não é atendido conforme a declaração. |
| Vínculo com o runtime ativo | A usuária atestou o destino pretendido, mas falta registro datado e mascarado da configuração efetivamente carregada pelo processo do piloto. |
| TLS efetivo | SSL Enforcement foi observado desligado; falta comprovação datada da conexão efetiva com TLS e verificação do servidor no ambiente identificado. |
| Continuidade | O plano Free não apresenta backups programados; falta mecanismo aplicável documentado e registro datado de restauração com integridade conferida em destino isolado. |

Para completar apenas a documentação, a pessoa responsável pela configuração
deve produzir, sem mostrar URL ou credenciais ao assistente, a atestação
mascarada do vínculo e a evidência TLS. O responsável pelo banco deve informar
o mecanismo de backup e apresentar o registro de um restore isolado verificado;
se ainda não existir, a execução precisa de proposta e autorização separadas.
Não consultar produção nem usar dados reais. Até lá, a Fase 32 permanece
**parcialmente homologada** e não há autorização para migration, testes
autenticados ou publicação nesta retomada.

### Solicitação pronta para a pessoa que administra o piloto e o banco

Pedir uma resposta datada, identificando a função do responsável (sem dados
pessoais de usuários do sistema), com **somente** os resultados abaixo:

1. A presença de embeddings reais e links em `xoof…esgx/main` foi confirmada
   pela operadora. Submeter finalidade, acesso, retenção e segregação dos dados
   à avaliação do controlador/DPO antes de qualquer teste. Não enviar linhas,
   fotos, embeddings ou capturas do banco.
2. Confirmar se a configuração **efetivamente carregada pelo processo do
   piloto** corresponde a `xoof…esgx/main`, informando apenas resultado
   sim/não, data, função do operador e identificador mascarado da instância.
   Conferir privadamente, sem compartilhar URL de conexão ou credenciais.
3. Informar se uma conexão real com esse ambiente negociou TLS com verificação
   do certificado/hostname, indicando data, método e resultado sanitizado.
   Caso a prova exija consulta remota, solicitar nova autorização antes.
4. Informar qual backup é aplicável a esse projeto Free e apresentar, **se já
   existir**, registro datado de restauração em destino isolado, com origem e
   destino mascarados e checagem de integridade sem conteúdo dos dados. Se não
   existir, responder “não realizado”; não acionar Restore no projeto ativo.

Não pedir nem enviar `DATABASE_URL`, senhas, tokens, chaves, tela `Connect`,
SecureString ou arquivos de ambiente. A ausência de qualquer resposta mantém
a barreira documental; executar backup, restore, consulta remota ou sessão AWS
requer tarefa e autorização próprias.

## Atualização de continuidade — 24/10/2026

A declaração antiga de dados exclusivamente fictícios foi corrigida pela
operadora: `xoof…esgx/main` contém biometria real de participantes do piloto.
Com autorização específica, a operadora criou um dump lógico cifrado com GPG,
usando `pg_dump 17.11`, TLS `verify-full` e CA oficial verificada; o SHA-256 do
artefato é
`b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f`.
O arquivo cifrado passou na validação de formato com `pg_restore 17.11`.
O restore integral não concluiu por extensão interna do Supabase ausente na
imagem local, mas o schema `public` e seus dados foram restaurados com êxito
em PostgreSQL 17/pgvector isolado, sem rede ou porta publicada. Nenhuma linha
foi exibida. Backup e destino local foram preservados. Isso protege e valida
parcialmente o schema da aplicação, não comprova restore integral dos schemas
internos nem continuidade remota do Supabase Free. Os originais das fotos no
Cloudinary não fazem parte do dump.

A sequência local `001`–`026` foi reconfirmada sem lacunas. Em 24/10, os testes
locais da Fase 33 (5 executados, 2 opt-in ignorados), Fase 34 (17 executados,
3 opt-in ignorados) e TLS (4 executados) passaram. A sessão do perfil AWS
restrito expirou antes da primeira tentativa de consulta remota. Depois, a
operadora renovou o login e autorizou uma sessão de inspeção da EC2 existente.
O SSM confirmou o script de boot que consulta o ponteiro privado S3 e usa a
chave fixa anterior apenas como fallback. O serviço `frequenia.service`
estava ativo. A sessão foi encerrada pelo controlador e a EC2 foi confirmada
em `stopped`, com 75 segundos adicionais registrados na cota. Não houve
troca de imagem, migration, teste autenticado ou habilitação facial. A Fase 32
continua **parcialmente homologada**.

### Diagnóstico posterior do schema atual — 24/10/2026

Em consulta somente ao catálogo do projeto `xoof…esgx/main`, conduzida pela
operadora sem expor credenciais ou linhas pessoais, os marcadores retornaram
`biometria_base=1`, `migration_025_presente=1` e
`migration_026_ausente=0`. A conferência complementar da `026` retornou
`tabelas=1`, `colunas=1`, `indices=1`, `gatilhos=1` e `restricoes=1`.
Portanto a estrutura conferida da `026` **já estava presente**; o assistente
não a aplicou nem conhece sua data ou origem. Não reaplicar a migration.
Permanecem pendentes a validação da nova imagem no piloto, o vínculo/TLS
efetivos do runtime e os testes autorizados. O facial segue desabilitado.

Após autorização separada, o ponteiro privado S3 foi atualizado com condição
de ETag para a imagem imutável candidata `7adc…2caf`; leitura posterior
confirmou a chave exata e o ETag `d2454566a4305d9135af93d4718e60b0`.
A imagem anterior permanece no mesmo bucket para rollback. Nenhuma stack,
EC2, banco ou política biométrica foi alterada nesta etapa; o boot e a
validação do piloto ainda dependem de confirmação própria.

Em duas sessões controladas posteriores, a instância leu o ponteiro novo,
mas app/dispatcher/worker continuaram executando a tag `frequenia:pilot`
anterior. O diagnóstico mostrou que o pacote S3 carregou outra tag,
`frequenia:pilot-20261023-retention`, sem substituir a tag usada pelos
serviços. O ID carregado na EC2 também não coincide com o ID local registrado
no build. A publicação da imagem nova permanece **não validada**. Nenhum
retag ou reinício foi feito; a EC2 foi encerrada e confirmada `stopped`.

O pacote local corrigido foi preparado sem nova operação AWS: o manifesto
agora contém apenas `frequenia:pilot`, tag consumida pelos serviços, e o
config ARM64 `sha256:5ce47f2d…a1489`, que coincide com a imagem versionada
carregada na EC2. O gzip passou na validação integral. O pacote novo tem
SHA-256 `89b5980f599223a0fd2430700278e1ded5f421b5862faed022c02314e4c1b3f0`.
Ele ainda não foi enviado ao S3 nem selecionado pelo ponteiro.

Após autorizações específicas posteriores, o pacote corrigido foi enviado
para nova chave imutável no bucket privado existente e o ponteiro foi trocado
condicionalmente para ela. O objeto remoto tem 920.166.719 bytes, metadado
SHA-256 declarado igual ao hash local e SSE-S3/AES256; o ETag multipart não
foi usado como prova de hash. A leitura posterior confirmou a chave corrigida
e a EC2 permaneceu `stopped`. O boot e a validação real da imagem nova ainda
não ocorreram, e o reconhecimento facial não foi ativado.

No boot controlado posterior, a tag correta foi efetivamente carregada, mas o
aplicativo reiniciou por ausência de `openpyxl` no manifesto de dependências
ARM64; a falha foi classificada sem exibir logs sensíveis. A EC2 foi novamente
encerrada e confirmada `stopped` (47.987/144.000 segundos). O manifesto de
runtime e o smoke test do Dockerfile foram corrigidos localmente. Os testes de
infraestrutura (11) e da Fase 34 (14) passaram, e uma imagem ARM64 derivada da
candidata validada confirmou os imports em container isolado sem rede. O novo
pacote local, ainda não enviado, tem 920.661.754 bytes, SHA-256
`fb58666254fae4a08baa71b3b18bdc981919cdb92087874c0597c55504eab082`,
tag única `frequenia:pilot` e config `sha256:df86bf72…5ed537`. A Fase 32
permanece parcialmente homologada até novo boot e validação do piloto.

Após confirmação específica, o pacote do hotfix foi enviado para uma nova
chave imutável no bucket privado existente. A verificação remota confirmou
920.661.754 bytes, SSE-S3/AES256 e metadado SHA-256
`fb58666254fae4a08baa71b3b18bdc981919cdb92087874c0597c55504eab082`.
O ponteiro, a EC2, o banco e o plano não foram alterados nesta ação; as imagens
anteriores foram preservadas para rollback.

Com confirmação específica posterior, o ponteiro foi atualizado de forma
condicional para a chave imutável do hotfix. A leitura remota confirmou a chave
exata; a EC2 permanece `stopped`, `t4g.small`, ARM64. A mudança só terá efeito
no próximo boot autorizado. Banco, plano, stack e ativação facial permaneceram
inalterados, com as imagens anteriores preservadas para rollback.

Em sessão controlada autorizada, o piloto carregou e executou o hotfix com o ID
esperado `sha256:df86bf72…5ed537`, ARM64/Linux. Serviço e cinco containers
ficaram ativos com zero reinícios; HTTPS, `/health` e `/ready` passaram. A
checagem sanitizada confirmou em booleanos o projeto Supabase esperado,
`verify-full`, CA legível e TLS cliente ativo, sem exibir conexão ou dados. Não
houve migration, autenticação de usuário ou uso facial. A sessão SSM foi
encerrada e o controlador confirmou a EC2 em `stopped`, sem trava de custo,
com 48.156/144.000 segundos. A publicação técnica da imagem está validada; a
homologação funcional autenticada e a decisão LGPD continuam separadas.

Na sessão funcional posterior, o reconhecimento 1:1 avançou até o motor de
jornada, que bloqueou corretamente a marcação como `sem_jornada`. O snapshot
de 25/10/2026 já estava materializado e permaneceu imutável. A operadora
informou ter preparado uma escala temporária para 26/10/2026, data em que a
marcação completa ainda deverá ser validada. Ao final, o controlador confirmou
a EC2 em `stopped`, sem trava de custo, com 52.557/144.000 segundos utilizados.

Na sessão autorizada de 26/10/2026, a EC2 existente iniciou sem criação de
recursos; HTTPS apresentou validação TLS bem-sucedida e `/health` e `/ready`
retornaram `200`. A participante autorizada informou que o fluxo facial no APK
registrou o ponto corretamente na jornada do dia. Nenhuma linha pessoal foi
consultada pelo assistente. O resultado conclui a validação funcional da
marcação facial; relatórios e exportações permanecem uma validação separada.
