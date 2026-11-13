# Publicação AWS das alterações existentes

Data: 2026-10-16 (America/Sao_Paulo)

## Estado

Publicação **ainda não aplicada**. A preparação local foi concluída, mas a
identidade AWS ativa é `root`; por segurança e pelas regras desta publicação,
nenhuma mutação foi executada. É necessário autenticar uma identidade temporária
com MFA e privilégio mínimo antes de criar os change sets.

O `aws login --profile frequenia-pilot-publish`, autorizado pelo usuário em
2026-10-16, concluiu com credenciais temporárias, mas a identidade retornada
continuou sendo `root`. O perfil preexistente `frequenia-new` também foi
verificado de forma somente leitura e resolve para `root`. Nenhum dos dois foi
usado para mutações.

## Identidade, regiões e piloto observado

- conta AWS: `********8156`;
- identidade observada: `root` (recusada para publicação);
- regiões: `sa-east-1` (runtime) e `us-east-1` (billing);
- stacks existentes: `frequenia-pilot-artifacts-sa`,
  `frequenia-pilot-attachments`, `frequenia-pilot-runtime`,
  `frequenia-pilot-artifacts-us` e `frequenia-pilot-budget`, todas em
  `CREATE_COMPLETE` na consulta prévia;
- EC2: `i-0b05f77cae35912f8`, `t4g.small`, ARM64, `sa-east-1a`, observada
  `stopped`;
- parâmetros `/frequenia/pilot/runtime-env` e
  `/frequenia/pilot/duckdns-token`: existem como `SecureString`; os valores não
  foram consultados.

## Estado local e artefato candidato

- branch: `desenvolvimento-mvp`;
- HEAD: `e3d33f6c13a9974ec8318e37312591f2696aeb16`;
- checkout: sujo, com 178 entradas em `git status --short`; todas tratadas como
  alterações preexistentes e preservadas;
- imagem: `infra/aws/dist/frequenia-arm64-pilot-candidate-20261016.tar.gz`;
- SHA-256 do arquivo: `67ab2cd1481b85eb325a4aac45e4410489fd13a029f80d0cd943bf1d04e30619`;
- digest da imagem: `sha256:67fcf356c67fe52885f051de195b85ce21670dd414f76f5be04a409cf337e89a`;
- arquitetura confirmada: `arm64`;
- inventário `/app`: 175 arquivos, sem `.env`, `.secrets`, credenciais,
  chaves, caches, temporários, dumps, backups, APK ou metadados Git;
- comparação do conteúdo da imagem com o checkout: 0 arquivos ausentes na
  origem e 0 divergências de SHA-256;
- presentes na imagem: migration `026`, motor de jornada, governança
  biométrica, dispatcher e worker de anexos.

## Ajustes estritamente operacionais preparados

- runtime passa a usar a SQS privada existente, com policies já produzidas pela
  stack de anexos;
- dispatcher e worker passam a executar em containers separados do Gunicorn,
  com supervisão `restart unless-stopped`, limite de memória e tratamento de
  encerramento;
- readiness de publicação passa a exigir `/ready`, dispatcher e worker ativos;
- `BIOMETRIC_AWAY_POLICY` fica explícita e restrita aos valores já suportados;
- imagem passa a ser armazenada sob chave privada imutável contendo seu SHA-256;
  a verificação remota usa metadado SHA-256, nunca igualdade de tamanho;
- a imagem é carregada a cada boot para impedir reutilização de tag local antiga;
- o pipeline recusa credenciais AWS root e mascara a conta exibida.

## Validações locais realmente executadas

- backend: 354 testes, 257 sucessos, 97 skips opt-in explícitos, 0 falhas;
- testes focados de infraestrutura/configuração/readiness: 21/21;
- parser PowerShell de `deploy.ps1`: sem erros;
- `git diff --check`: sem erros;
- `cfn-lint`: sem erros; dois avisos `W3002` esperados para os caminhos locais
  de Lambda em `runtime.template.yaml`, resolvidos pelo `cloudformation package`;
- `cfn-guard` e `gitleaks`: não instalados; nenhum resultado foi inventado;
- migrations: sequência contínua `001`–`026`; `026` é a última.

## Change sets previstos (não criados)

- `frequenia-pilot-runtime` (`sa-east-1`): alteração da role existente para
  anexar as policies SQS existentes, parâmetros da fila/política biométrica,
  atualização do UserData e chave imutável da imagem. O change set deve confirmar
  ausência de replacement da EC2 antes da aplicação;
- stacks de artefatos, anexos e billing: não se espera alteração material; um
  change set vazio é o resultado desejado caso sejam comparadas;
- nenhum recurso novo, stack nova, VPC, ALB, NAT, RDS, ECR, CMK ou domínio será
  criado.

## Banco e migrations

A migration `026` ainda não foi aplicada remotamente nesta execução. Antes disso
é obrigatório comprovar que o destino é um banco/branch exclusivo de homologação,
com TLS, backup e restore verificado. O valor de `DATABASE_URL` não foi lido nem
exibido. Se o banco estiver em `025`, o upgrade `025 → 026` será testado primeiro
em clone/branch. Nenhum acesso a produção ou dado real foi realizado.

## Plano de rollback

1. manter o objeto privado anterior no S3 e publicar o candidato em nova chave
   imutável;
2. não executar change set que indique replacement inesperado ou mudança fora do
   runtime/IAM/SQS previstos;
3. em falha de readiness ou fluxo principal, restaurar a chave anterior da
   imagem e o template anterior do runtime;
4. em falha de migration, interromper a abertura do piloto e restaurar o clone de
   homologação validado; não reverter schema automaticamente;
5. encerrar a sessão pelo controlador existente e confirmar a EC2 `stopped`.

## Custos e limitações

Permanecem custos residuais potenciais de EBS, S3 (incluindo o artefato anterior
preservado), DynamoDB, SQS, SNS, CloudWatch e Budgets. O budget e os limites de
sessão/horas existentes serão preservados. Não haverá teste de carga. Resultados
de capacidade ou biometria do piloto não serão apresentados como SLO ou precisão
de produção.

## Resultados externos

Pendentes: change sets revisados/aplicados, backup/restore do banco de
homologação, migration `026`, HTTPS/readiness, autenticação/RBAC, jornada e
concorrência, Gestor → RH, visão efetiva, anexos/scan/download, biometria 1:1,
estados/desligamento da Fase 31, independência de `falha_facial`, isolamento de
tenant e não enumeração. A URL e os resultados serão registrados após execução.

## Evidências posteriores verificadas em 20/10/2026

Esta atualização preserva o histórico de 16/10 e registra somente fatos
comprovados posteriormente. O ponteiro privado
`runtime/current-image-key.txt`, atualizado em 19/10, aponta para
`runtime/frequenia-arm64-be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa.tar.gz`.
O objeto possui 919.741.243 bytes, SSE-S3/AES256 e metadado SHA-256
`be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa`.

Também foram encontrados no S3 um script de boot imutável de 19/10 que fixa
essa chave e um instalador que, se executado na EC2, altera o boot local para
consultar o ponteiro na próxima inicialização. A política do usuário publisher
não permite ler `UserData` nem histórico SSM; portanto a execução do instalador
e a imagem efetivamente carregada continuam não comprovadas. A EC2 ARM64
`t4g.small` foi observada em `stopped`.

O APK privado `1.0.0-pilot.1` teve o SHA-256 publicado confirmado, mas é de
14/10, usa certificado Android Debug e antecede dois commits que alteraram
`mobile/` em 17/10. Ele está defasado em relação ao HEAD inspecionado. Detalhes,
limitações e resultados locais estão em `FASE_32_HOMOLOGACAO_PILOTO_AWS.md`.

Em 21/10 foi aberta uma sessão de aproximadamente dez minutos pelo controlador
existente. HTTPS e `/health` responderam 200; `/ready` passou de 503 enquanto as
assinaturas ClamAV eram atualizadas para 200 com storage, SQS, scanner e
assinaturas saudáveis. As rotas das Fases 30 e 31 existem na aplicação ativa,
excluindo operacionalmente a imagem legada de 14/10, mas o digest Docker não
pôde ser lido por falta de acesso SSM. A sessão foi encerrada pelo controlador e
a EC2 foi confirmada em `stopped`. Testes autenticados e migration remota não
foram executados porque banco exclusivo de homologação, TLS e backup/restore
ainda não foram comprovados.

## Preparação local em 22/10/2026 — candidato ainda não publicado

- Imagem `frequenia:pilot-20261022-face-lgpd`, arquitetura ARM64 e inventário
  obrigatório validados localmente; digest Docker
  `sha256:d211ff8f190e7007d3629b1779e0d63cd7af94d3c0075e669131f829388c4970`.
- Pacote local `infra/aws/dist/frequenia-arm64-pilot-candidate-20261022-face-lgpd.tar.gz`:
  920.166.326 bytes, SHA-256
  `9779d343f0171b08e43f16047680974acb31c66d16c3051a497f1dea6b33b01d`;
  `gzip -t` passou.
- O runtime candidato incorpora CA pública do Supabase conferida por SHA-256 e
  configura `sslmode=verify-full`. Isso ainda não comprova TLS efetivo no banco
  do piloto.
- Integrações locais Fase 31: 13/13; Fase 33: 2/2. Os testes usaram PostgreSQL
  descartável, removido ao final; não equivalem a testes autenticados no piloto.
- Com autorização expressa da usuária, os pacotes locais de 14/10 e 16/10
  foram removidos para liberar espaço. O pacote de 17/10 foi preservado como
  candidato de rollback local; o objeto anterior no S3 não foi alterado.
- A controladora declarou a intenção de guardar biometria para treinamento
  futuro. O fluxo atual não treina modelos nem persiste fotos; o uso futuro é
  finalidade adicional pendente de política, prazo, fundamento e implementação,
  conforme `FASE_33_RECONHECIMENTO_LGPD.md`.

Migration `026`, backup remoto/restore, troca do ponteiro, abertura do piloto e
ativação facial continuam pendentes de suas etapas controladas.

Consulta AWS somente leitura em 22/10/2026, após login da própria usuária:
perfil `frequenia-pilot-publish`, principal `frequenia-publisher`, conta
`********8156`. A stack de runtime e a de artefatos estavam em
`CREATE_COMPLETE`, a de anexos em `UPDATE_COMPLETE`, e a EC2 `t4g.small` em
`stopped`. O pacote novo ainda não existia no S3. O ponteiro privado atual
permanecia na imagem de SHA-256
`be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa`.
Esses metadados não comprovam o digest efetivamente executado pela EC2 nem o
vínculo do runtime com o Supabase.

Após confirmação específica da usuária em 22/10/2026, o pacote foi enviado
para uma **chave nova** no bucket privado existente. `head-object` confirmou
920.166.326 bytes, `ServerSideEncryption=AES256` e metadado SHA-256 igual ao
hash local `9779d343f0171b08e43f16047680974acb31c66d16c3051a497f1dea6b33b01d`.
O ponteiro continuou apontando para
`be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa`.
Esse upload não instalou a imagem, não executou migration e não iniciou a EC2.
O script local `pilot-session.ps1` passou a selecionar explicitamente o perfil
operacional `frequenia-pilot-publish`; o parser PowerShell passou. Nenhuma ação
`start`, `renew` ou `stop` foi invocada nesta preparação.

## Candidata local posterior — 23/10/2026

O código local ganhou bloqueio de verificação 1:1 para embedding vencido pelo
prazo da política. A suíte local passou 382 testes, com 102 skips; a integração
com PostgreSQL/pgvector descartável no Docker do WSL passou 14/14, incluindo
uso dentro do prazo e recusa após o vencimento. O contêiner foi encerrado.

O build ARM64 local incluiu apenas
`static/img/brand/frequenia-logo-white-v4.png` entre os PNGs de marca não
rastreados, pois é o único referenciado pelos templates e permitido pelo
`.dockerignore`. Os demais ficaram fora. O empacotamento passou a comprimir
diretamente no WSL, sem tar intermediário na unidade C:.

- pacote: `infra/aws/dist/frequenia-arm64-pilot-candidate-20261023-retention.tar.gz`;
- tamanho: 920.166.730 bytes;
- SHA-256: `7adc75383fd30057de4275fd57dce88a8aa5aea58fdd53e70b39c6eca60e2caf`;
- digest informado pelo Docker: `sha256:915e0bc7af2e8f1f259897c62dd9b409a74be66854babd10c405926298f62f97`;
- arquitetura: ARM64; inventário: 149 arquivos em `/app`, sem caminhos proibidos.

O objeto de 22/10 com
SHA-256 `9779d343f0171b08e43f16047680974acb31c66d16c3051a497f1dea6b33b01d`
continua anterior à correção. A existência de dados faciais reais no Supabase
corrigiu a premissa inicial de dados somente sintéticos; o `AGENTS.md` foi
atualizado após autorização da usuária em 23/10. Não houve consulta ao banco,
migration ou teste autenticado no piloto.

### Upload autorizado em 23/10/2026

Após confirmação específica, a candidata de SHA-256 `7adc7538…60e2caf` foi
enviada para uma **nova chave imutável** no bucket privado já existente em
`sa-east-1`. A primeira tentativa, em requisição única, foi interrompida após
longa espera sem objeto concluído; o reenvio multipart terminou sem erro.
`head-object` confirmou 920.166.730 bytes, metadado SHA-256 completo igual ao
hash local e criptografia SSE-S3/AES256. O objeto anterior de SHA-256
`be1d958a…556aa` continua presente. A leitura do ponteiro
`runtime/current-image-key.txt` confirmou que ele **ainda aponta para o objeto
anterior**. A EC2 foi consultada em `stopped` e a stack de runtime em
`CREATE_COMPLETE` antes do upload. Nenhum change set foi criado/aplicado,
nenhuma sessão do piloto foi iniciada, nenhuma migration foi aplicada e o facial
não foi ativado. O perfil operacional usado foi `frequenia-publisher` na conta
mascarada `********8156`.

Na preparação posterior, `get-template-summary` da stack existente confirmou
tipos de recursos e nomes de parâmetros sem consultar segredos. A stack
implantada ainda usa `ContainerArchiveKey=runtime/frequenia-arm64.tar.gz`;
portanto, o upload da imagem **não atualiza o boot**. O template local de
runtime foi validado com `cfnlint.api`: 0 erros e 2 avisos `W3002` esperados
para Lambdas a empacotar. Nenhum change set foi criado. O redeployment global
de `deploy.ps1` não deve ser usado nesta continuidade: ele reimplanta outras
stacks e sobrescreve parâmetros SSM, além do escopo do passo atual.

### Separação do backup de biometria e fotos — 23/10/2026

A operadora esclareceu que o Supabase `xoof…esgx/main` guarda embeddings e
links das fotos, mas os arquivos originais estão no Cloudinary. Isso foi
declarado, não verificado com abertura de links ou imagens. Um dump lógico do
banco **não inclui** os originais do Cloudinary. Antes da migration remota,
deve-se obter o backup lógico protegido do banco e provar restauração isolada;
em paralelo, o operador deve verificar a cobertura dos originais do Cloudinary
sem expor os arquivos ao assistente. O estado de backup dessa conta Cloudinary
ainda não foi consultado, e nenhuma alteração foi feita nela. A documentação
atual do Cloudinary informa que backup automático é desligado por padrão,
existe em todos os planos, consome cota de armazenamento e exige uma operação
separada para cobrir assets anteriores; portanto não se presume que as fotos
antigas estejam protegidas. Referência:
https://cloudinary.com/documentation/backups_and_version_management .

### Revisão do change set sem execução — 23/10/2026

Com confirmação específica da usuária, somente os dois pequenos pacotes Lambda
do runtime foram enviados ao bucket privado já existente (4.604 e 3.699 bytes).
O template empacotado local
`infra/aws/.generated/runtime.review-20261023.yaml` tem SHA-256
`2770951fa5a4603a970037a3b5864099dfdbad45e312ab30aa4ab973271924d2`
e passou em `cloudformation validate-template`. Foi criado, mas **não
executado**, o change set `frequenia-pilot-20261023-face-review` da stack
existente `frequenia-pilot-runtime`.

A revisão encontrou 10 modificações, sem recurso novo, mas `PilotInstance`
apresentou `Replacement=True`. A propriedade decisiva é `ImageId`
(`RequiresRecreation=Always`); `UserData` também aparece como mudança
condicional. O template implantado usa referência dinâmica à AMI Amazon Linux
mais recente; a EC2 atualmente parada usa uma AMI específica. Como o change
set viola a exigência de preservar a EC2, **não deve ser executado**. Nenhuma
stack, instância, ponteiro ou configuração de banco foi alterada.

Foi preparado apenas localmente um parâmetro opcional para fixar a AMI atual
em uma futura revisão sem recorrer à referência dinâmica durante esta
atualização. `cfn-lint` local retornou 0 erros e 2 avisos W3002 esperados dos
diretórios Lambda; os 10 testes locais de infraestrutura AWS passaram. O
parâmetro tem valor vazio por padrão, preserva a seleção dinâmica em novas
instalações e não fixa um ID regional no Git. Essa hipótese ainda precisa ser comprovada por um novo
change set; não autoriza sua criação nem execução. Após a preocupação da
usuária com custo, nenhuma outra mutação remota será feita sem apresentação
prévia do efeito e nova confirmação. Não houve mudança de plano AWS.

Para uma eventual segunda revisão, o template empacotado foi ajustado **apenas
localmente**, reutilizando as duas referências S3 dos pacotes Lambda já
enviados. SHA-256 local resultante:
`aac33f98b798a028eee1a6e9f5d7cf34cb36494d6e7a1def82bb0a95718c9880`.
`cfn-lint` do template empacotado: 0 erros, 0 avisos. Esse hash não pertence ao
change set anterior.

Após confirmação específica, o template foi submetido como segundo change set
de revisão `frequenia-pilot-20261023-ami-pin-review`, **sem execução**. Ele
ficou `CREATE_COMPLETE/AVAILABLE`, com 10 modificações e nenhum recurso novo.
Entretanto, `PilotInstance` ficou com `Replacement=Conditional`: o detalhe
`ImageId` aparece como `RequiresRecreation=Always`, com avaliação dinâmica de
referência ao novo parâmetro; `UserData` permanece condicional. Isso **não
comprova** preservação da EC2 e viola o requisito de change set sem
replacement, portanto o segundo change set também não deve ser executado.
O parâmetro experimental foi retirado do template-fonte local após a revisão;
o artefato empacotado ignorado pelo Git e o change set não executado foram
mantidos somente como evidência. Nenhuma stack ou instância foi alterada. O próximo passo é estabelecer um
caminho operacional comprovado para atualizar a imagem na EC2 existente ou
reformular o template de modo que uma nova revisão mostre
`Replacement=False` para a instância; qualquer sessão/ação remota exige nova
confirmação. Depois de confirmação específica da usuária, os dois change sets
**não executados** foram excluídos por nome para impedir aplicação acidental.
Cada `delete-change-set` terminou sem erro; a consulta individual posterior
de cada nome retornou `ChangeSetNotFound`, e a stack continuou em
`CREATE_COMPLETE`. O perfil operacional negou `ListChangeSets`, de modo que
não houve inventário global de outros planos. Os resumos sanitizados acima
preservam a evidência dos dois planos excluídos. A imagem imutável no bucket,
o ponteiro anterior, a EC2 e o banco não foram apagados ou alterados por essa
exclusão.

O caminho alternativo mais estreito, ainda **não autorizado nem verificado**,
é inspecionar durante uma sessão controlada qual script de boot está realmente
instalado na EC2 existente. Se ele já resolver o ponteiro privado
`runtime/current-image-key.txt`, uma troca condicional desse ponteiro pode
selecionar a imagem imutável no boot seguinte sem update de CloudFormation;
se o boot continuar fixado em outra chave, a troca isolada do ponteiro não terá
efeito. Não se deve testar isso por tentativa com os dados reais. A inspeção
exige abertura da EC2 e tempo de computação, além da barreira de backup/TLS do
banco e das confirmações específicas já descritas.

### Evidência de continuidade ainda necessária antes de abrir o piloto

No plano Free, a documentação oficial do Supabase recomenda exportação lógica
periódica com `supabase db dump`; o painel não fornece backup diário. Para o
projeto atual com dados biométricos reais, a operação deve ocorrer em máquina
confiável sob responsabilidade da operadora, com credencial introduzida sem
exposição ao assistente, ao histórico de comandos ou ao Git. Registrar apenas
versão da ferramenta, horário, operador, hash dos arquivos protegidos e
resultado do restore **local isolado**, sem publicar linhas, links, fotos,
vetores ou URL. O restore local é salvaguarda de publicação, não prova de
continuidade remota do Supabase. Não há autorização para criar outro projeto
nem restaurar sobre o ativo. Referências oficiais:
https://supabase.com/docs/guides/platform/backups e
https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore .
Em 23/10/2026, perguntada sobre backup lógico posterior aos cadastros faciais
e restore isolado testado, a usuária respondeu **“não sei”**. Portanto ambos
permanecem **não comprovados**; não se deve presumir que o backup do Cloudinary
proteja as linhas do Supabase. Nenhuma exportação ou restauração foi iniciada
pela assistente.

Em separado, a operadora deve confirmar no Cloudinary se o backup automático
está ligado **e** se o job de backup dos assets preexistentes terminou; o
status ainda não havia sido informado na revisão anterior. Em resposta de
23/10/2026, a usuária respondeu “sim” à pergunta conjunta sobre as duas
condições. Isso fica registrado como **declaração da operadora**, sem inspeção
do painel, identificação do job, data de conclusão ou teste de recuperação;
não é evidência técnica suficiente de proteção dos originais. Ativar essas opções pode aumentar o consumo
de armazenamento e replicar fotos reais, portanto exige decisão específica
de custo, finalidade, acesso e prazo antes de alterar a configuração.

## Retomada solicitada em 22/10/2026 — banco atual com dados reais

A usuária pediu continuar a publicação para testar, mantendo o Supabase atual,
e declarou que nele há dados faciais reais seus e de mais uma pessoa, que ela
informa ter aceitado participar. Essa declaração corrige a premissa anterior
de dados exclusivamente sintéticos; o registro da aceitação da outra pessoa
não foi examinado. Nenhuma foto ou embedding foi consultado, enviado ou
alterado. O piloto pretendido continua limitado a verificação 1:1, sem
treinamento de IA nesta janela.

A preparação local e os testes sem dados reais podem prosseguir. A instrução
operacional vigente proíbe acessar ou escrever no banco ao aparecer indício de
dados reais. Além disso, identidade ativa do banco, TLS efetivo e restauração
isolada seguem sem comprovação, e a avaliação de privacidade e retenção ainda
não foi formalizada. Portanto, o pedido não equivale a aprovação para
executar migration `026`, trocar o ponteiro, abrir sessão com dados reais ou
habilitar facial. Preservar a imagem anterior e os dados existentes até decisão
específica sobre um plano de teste real que trate essas lacunas.

Revalidação **somente local** nesta retomada: 21/21 testes focados de biometria,
relatórios e TLS passaram; a suíte `python -m unittest discover -s tests -p
'test_*.py'` executou 380 testes, com 102 skips previstos e nenhuma falha.
Isso não substitui validação do pacote ARM64 no piloto nem autoriza acesso ao
banco remoto.

## Backup do banco atual e restauração local — 24/10/2026

Com a operadora digitando a credencial e a frase secreta somente no PowerShell
particular, foi produzido um dump lógico do projeto vinculado `xoof…esgx/main`
com `pg_dump 17.11`, TLS `verify-full` e CA oficial conferida por SHA-256. O
artefato foi cifrado em fluxo com GPG AES-256 na pasta privada fora do Git.
A criação ocorreu às 16:45:27 (America/Sao_Paulo); o arquivo final tinha
500.395 bytes e SHA-256
`b2d6931667ed4d07ee593c48fb04aed6b5d203eec4d97ee3c2c0ca85ae79081f`,
recalculado independentemente. Não se registraram URL, senha, frase secreta,
fotos, links, embeddings ou linhas do banco.

A operadora autorizou especificamente o restore local. O arquivo cifrado passou
na descriptografia e na leitura de formato por `pg_restore 17.11`. A restauração
integral em PostgreSQL 17/pgvector isolado **não concluiu**: a imagem local não
contém uma extensão interna exigida pelo dump do Supabase. Uma nova base vazia
no mesmo contêiner, com `pgcrypto` e `vector`, restaurou com exit code zero o
schema `public` e seus dados; a checagem de catálogo confirmou tabelas. Nenhuma
linha foi exibida ou consultada pelo assistente. O contêiner ficou sem rede e
sem porta publicada, com volume persistente; após a saída do WSL, seu estado
observado era `exited`. O backup, o contêiner e as bases isoladas foram
preservados, sem exclusão automática.

Resultado: há salvaguarda lógica e restore **parcial validado do schema da
aplicação**, que é o escopo da migration `026`. Não existe prova de restore
integral dos schemas gerenciados pelo Supabase nem de continuidade remota do
serviço Free. O dump também não inclui os arquivos originais no Cloudinary.
Nenhuma migration, alteração AWS, troca de ponteiro ou ativação facial foi
executada neste passo. O disco C: tinha cerca de 757 MiB livres após o teste;
evitar novos downloads/imagens antes de liberar espaço de forma autorizada.

## AWS após renovação do login — 24/10/2026

A operadora concluiu pessoalmente o login remoto do perfil restrito
`frequenia-pilot-publish`. Consulta somente leitura confirmou o principal
`frequenia-publisher` na conta mascarada `********8156`, a EC2 existente
`i-0b05f77cae35912f8` em `stopped`, a stack `frequenia-pilot-runtime` em
`CREATE_COMPLETE`, o objeto candidato imutável no S3 privado e o ponteiro
ainda na imagem anterior. O controlador respondeu `ok:true`, sem trava de
custo, com 35.871 de 144.000 segundos usados na cota mensal configurada.
Isso não comprova ausência de cobrança AWS.

O mesmo perfil recebeu `AccessDenied` para `iam:ListAttachedUserPolicies` e
`ssm:DescribeInstanceInformation`. Não houve alteração de IAM. O template
local fixa `ContainerArchiveKey` dentro do instalador de boot; portanto a
troca isolada do ponteiro S3 não é uma implantação comprovada. A versão
efetivamente instalada na EC2 e a possibilidade de sessão SSM continuam
desconhecidas. Não iniciar a máquina apenas para tentar um acesso cuja
permissão não está comprovada; obter acesso operacional limitado ou uma
alternativa verificável antes de propor uma sessão controlada. Nenhum recurso
AWS, banco ou facial foi alterado nesta retomada.

Após a operadora criar uma política em linha restrita no IAM, a consulta
`ssm:DescribeInstanceInformation` com o perfil `frequenia-pilot-publish`
passou sem `AccessDenied` e retornou lista vazia, coerente com a EC2 parada;
isso ainda não comprova que o agente SSM conectará após o boot. O plugin
oficial do Session Manager para Windows foi baixado da origem documentada
pela AWS, teve assinatura Authenticode válida de Amazon Web Services, Inc.
e foi instalado localmente com a participação da operadora; versão verificada
`1.2.896.0`. Nenhuma sessão SSM ou EC2 foi iniciada. O próximo passo exige
confirmação específica para iniciar a EC2 via controlador, observar o agente
SSM, inspecionar o boot sem imprimir segredos e encerrar confirmando `stopped`.

### Sessão de inspeção controlada — 24/10/2026

Com confirmação específica da operadora, o controlador iniciou somente a EC2
existente do piloto. O agente SSM apareceu `Online`; uma sessão com o principal
restrito confirmou, sem abrir `.env` ou parâmetros secretos, que o script
instalado `/usr/local/sbin/frequenia-boot` lê
`runtime/current-image-key.txt` em cada boot, valida o padrão da chave
imutável e a usa em `docker load`; a chave fixa da imagem anterior é apenas
fallback se o manifesto não existir. `frequenia.service` estava `active` e a
tag Docker local tinha ID `sha256:7ea5309c…f836a3`. O documento SSM padrão
nomeado explicitamente não existia nesta conta; a sessão padrão sem
`--document-name` funcionou.

A sessão SSM foi encerrada; o controlador recebeu `stop` e confirmou depois
`stopped`. A cota medida passou de 35.871 para 35.946 segundos (75 segundos).
Nenhuma imagem, ponteiro, stack, migration, configuração de banco ou chave
facial foi alterada. Esta inspeção estabelece um caminho técnico para a
publicação sem replacement da EC2: mudança controlada do ponteiro S3 para a
chave imutável já enviada, seguida de novo boot, com reversão para o valor
anterior se a validação falhar. As ações remotas posteriores exigem
confirmações específicas e salvaguardas de banco/LGPD.

Foi preparado, **mas não executado**, um script para a operadora aplicar
somente `026` no projeto atual depois de aprovação específica. Ele confere o
SHA-256 do backup cifrado, o vínculo mascarado, a CA, `verify-full` e os
marcadores de schema `025` presente/`026` ausente; pede senha em prompt privado
e uma confirmação textual antes do SQL. A saída completa fica em log privado
fora do Git, nunca no chat. A sintaxe Bash passou. SHA-256 do arquivo SQL
`026`: `39b46282182d269f5f2279d6fca5e1d36f75294c72229aaae6f700b412a7baa0`.
Não houve leitura de linhas pessoais nem aplicação de migration.

### Verificação de schema remoto — 24/10/2026

Após autorização específica para a migration `026`, o preflight privado da
operadora inicialmente falhou por DNS no WSL/Docker; nenhuma migration foi
iniciada. O DNS voltou a resolver. Na nova tentativa, a consulta somente ao
catálogo confirmou `biometria_base=1`, `025_presente=1` e `026_ausente=0`:
**a `026` já estava presente** no banco atual. O assistente não assumiu a
causa ou data dessa aplicação anterior e não tentou reaplicar SQL.

Diagnóstico complementar, também somente de catálogo e executado pela
operadora com senha privada, confirmou os cinco grupos esperados da `026`:
tabelas=1, colunas=1, índices=1, gatilhos=1 e restrições=1. Nenhuma linha,
embedding, foto, link ou URL foi consultado ou exibido. Isso comprova a
presença estrutural dos marcadores conferidos, não a integridade semântica de
todos os dados nem o histórico da migration. A imagem candidata continua no
S3 privado; o ponteiro ainda corresponde à imagem anterior, com ETag
`602e8ef3a9939612c6171d338a8e3cc3`; a EC2 segue `stopped`.

### Seleção da imagem candidata — 24/10/2026

Após confirmação específica da operadora, o ponteiro privado existente
`runtime/current-image-key.txt` foi atualizado condicionalmente pelo ETag
anterior para a chave imutável
`runtime/frequenia-arm64-7adc75383fd30057de4275fd57dce88a8aa5aea58fdd53e70b39c6eca60e2caf.tar.gz`.
A leitura posterior confirmou igualdade exata com a chave candidata; o novo
ETag é `d2454566a4305d9135af93d4718e60b0` (24/10/2026 21:18:13 UTC).
O objeto candidato já existia no bucket privado, tem 920.166.730 bytes,
metadado SHA-256 igual ao nome e SSE-S3/AES256. A chave anterior
`runtime/frequenia-arm64-be1d958aade6d0f6205105d0ae2758dd579cfab96b5340345ca188ad11f556aa.tar.gz`
foi preservada para rollback; não houve alteração de stack, plano, banco ou
EC2. A seleção só terá efeito no próximo boot da instância, que exige nova
confirmação. O reconhecimento facial continua desabilitado.

### Boot de validação não conclusivo — 24/10/2026

Após confirmação específica, o controlador iniciou a EC2 existente. O agente
SSM ficou `Online` e `frequenia.service` passou de `activating` para `active`;
app, dispatcher, worker, Caddy e ClamAV apareceram em execução. A leitura do
ponteiro feita de dentro da instância retornou a chave candidata, mas o ID
da tag Docker efetivamente usada por app/dispatcher/worker continuou
`sha256:7ea5309c…f836a3`, o mesmo da imagem anterior, e não o ID esperado
`sha256:915e0bc7…62f97`. A causa não foi determinada. Portanto a imagem nova
**não foi validada nem considerada publicada no runtime**. Não se fizeram
testes autenticados, consulta de dados reais ou ativação facial.

A inspeção adicional foi interrompida por falha do revisor automático da
ferramenta por limite de uso; não se buscou contornar essa revisão. O
controlador recebeu `stop`, e consulta posterior confirmou a EC2 em
`stopped`, sem trava de custo. A cota medida pelo controlador era 47.654 de
144.000 segundos. O ponteiro S3 permanece selecionando a candidata;
**antes de novo boot** é necessário decidir, com autorização específica,
se restaurá-lo para a chave anterior ou diagnosticar por que a imagem nova
não substituiu a tag ativa. Ambas as imagens seguem preservadas.

### Causa imediata identificada em nova sessão — 24/10/2026

Com nova confirmação específica, a EC2 foi iniciada apenas para diagnóstico.
O script instalado consulta a chave do ponteiro e executa `docker load` do
arquivo apontado, sem comando de retag. O journal sanitizado desta
inicialização mostrou `Loaded image: frequenia:pilot-20261023-retention`.
O inventário Docker da EC2 mostrou essa tag com ID `sha256:5ce47f2d…a1489`,
enquanto `frequenia:pilot` continuava em `sha256:7ea5309c…f836a3`.
Os serviços usam `frequenia:pilot`; logo o pacote não substituiu a tag que
eles executam. Não houve retag, reinício de serviço ou teste com dados.

Inspeção somente local no Docker do WSL mostrou que a tag
`frequenia:pilot-20261023-retention` agora tem ID
`sha256:915e0bc7…62f97`, diferente do ID visto na EC2 após carregar o
pacote S3. A identidade entre a imagem local atual e o conteúdo do pacote
publicado **não está comprovada**; o metadado SHA-256 do S3 confirma o hash
declarado do arquivo, não o ID Docker interno. Antes de publicar, gerar um
novo pacote verificável com a tag de runtime correta e comparar seu manifesto
e ID com a imagem local; não retaggear cegamente a imagem remota. A EC2 foi
encerrada pelo controlador e confirmada em `stopped`; ponteiro e imagens S3
não foram alterados nesta sessão.

### Pacote local corrigido — 24/10/2026

O Docker local do WSL ainda possui a imagem da candidata sob a tag
`frequenia:pilot-20261023-retention`. A tag local `frequenia:pilot`
preexistente foi preservada temporariamente como
`frequenia:pilot-pre-20261024`, a candidata recebeu a tag de runtime para
exportação, e a tag anterior foi restaurada depois. Nenhuma imagem local foi
apagada. O pacote novo é
`infra/aws/dist/frequenia-arm64-pilot-20261024-runtime-tag.tar.gz`, com
920.166.719 bytes e SHA-256
`89b5980f599223a0fd2430700278e1ded5f421b5862faed022c02314e4c1b3f0`.
O `gzip -t` integral passou. Seu manifesto Docker contém **somente** a tag
`frequenia:pilot` e config `sha256:5ce47f2d…a1489`; o config declara
`linux/arm64`. Esse config corresponde ao ID da tag versionada carregada
na EC2 na sessão diagnóstica. A diferença entre o ID informado pelo Docker
local (`sha256:915e0bc7…62f97`) e o config no arquivo decorre da distinção
entre os identificadores apresentados pelos formatos/stores, não prova
divergência de código por si só. A correspondência byte a byte com o pacote
S3 anterior não foi medida; o novo SHA-256 identifica este pacote corrigido.
Nenhum upload, ponteiro ou EC2 foi alterado nesta preparação.

### Upload e ponteiro corrigidos — 24/10/2026

Com autorizações específicas para as duas ações, foi enviado o pacote
corrigido para a nova chave imutável privada
`runtime/frequenia-arm64-89b5980f599223a0fd2430700278e1ded5f421b5862faed022c02314e4c1b3f0.tar.gz`.
A primeira tentativa falhou por conexão durante uma parte do multipart; não
criou objeto completo. O perfil restrito não possui
`s3:ListBucketMultipartUploads`, portanto a existência de partes temporárias
da tentativa não foi verificada. A segunda tentativa concluiu. `head-object`
confirmou 920.166.719 bytes, metadado SHA-256 igual ao hash local declarado
e SSE-S3/AES256. Como o ETag é multipart, ele não foi tratado como SHA-256
independente do conteúdo remoto.

O ponteiro anterior foi relido e seu ETag `d2454566a4305d9135af93d4718e60b0`
confirmado. Um `put-object` condicional selecionou a chave corrigida; a
leitura posterior confirmou igualdade exata e novo ETag
`b05c9a592fb5228df95663d07132992d`. A EC2 foi reconfirmada em
`stopped`. Nenhuma stack, banco, plano ou política biométrica foi alterada;
as imagens anteriores permanecem no S3. A imagem corrigida ainda precisa de
boot e validação no piloto antes de ser considerada publicada no runtime.

### Boot correto e dependência ausente — 24/10/2026

Na sessão controlada seguinte, o pacote corrigido carregou a tag de runtime
esperada `frequenia:pilot`, com config `sha256:5ce47f2d…a1489`. O aplicativo,
porém, reiniciou com código 3. O diagnóstico sanitizado classificou a falha
como `ModuleNotFoundError` para `openpyxl`; nenhuma linha de dados, segredo ou
variável de ambiente foi consultada ou exibida. A causa local confirmada foi
que `requirements.txt` já declarava `openpyxl==3.1.5` e
`et-xmlfile==2.0.0`, mas `requirements-runtime.txt`, usado pelo build ARM64,
não incluía essas dependências. O worker não chegou a iniciar. O controlador
encerrou a sessão e a EC2 foi confirmada em `stopped`, com 47.987 de 144.000
segundos registrados. Banco, stack, plano e política biométrica não foram
alterados.

### Hotfix local de runtime preparado — 24/10/2026

As duas dependências foram adicionadas ao manifesto de runtime e o
`Dockerfile.arm64` passou a validar os imports de `docx`, `openpyxl` e
`reportlab` durante o build. Os 11 testes de infraestrutura e os 14 testes da
Fase 34 passaram. Para evitar reconstruir sob QEMU todas as camadas já
validadas, foi gerada uma imagem derivada da candidata imutável, acrescentando
somente `et-xmlfile==2.0.0` e `openpyxl==3.1.5`; um container ARM64 isolado,
sem rede e com configuração sintética, confirmou os imports.

O pacote local resultante é
`infra/aws/dist/frequenia-arm64-pilot-20261024-openpyxl-hotfix.tar.gz`, com
920.661.754 bytes e SHA-256
`fb58666254fae4a08baa71b3b18bdc981919cdb92087874c0597c55504eab082`.
A leitura integral do tar gzip concluiu sem erro (29 entradas). O manifesto
contém somente a tag `frequenia:pilot` e config
`sha256:df86bf72…5ed537`. Nenhuma operação AWS ou no banco foi executada nesta
preparação; upload, seleção do ponteiro e novo boot ainda exigem confirmações
específicas.

### Upload do hotfix — 24/10/2026

Com confirmação específica da operadora, o pacote foi enviado à chave privada
imutável
`runtime/frequenia-arm64-fb58666254fae4a08baa71b3b18bdc981919cdb92087874c0597c55504eab082.tar.gz`.
O `head-object` confirmou 920.661.754 bytes, SSE-S3/AES256 e metadado SHA-256
igual ao hash local declarado. O ETag multipart
`c1674cd9735e34bdeb5a452aba999a35-110` não foi tratado como hash independente.
O ponteiro não foi alterado, a EC2 permaneceu parada e não houve operação no
banco ou mudança de plano. Pelo preço público vigente do S3 Standard em São
Paulo, o objeto isolado representa aproximadamente US$ 0,035 por mês de
armazenamento, antes de créditos, além de menos de US$ 0,001 em requisições no
upload. As imagens anteriores permanecem disponíveis para rollback.

### Seleção do hotfix — 25/10/2026

Após nova autenticação do perfil restrito `frequenia-publisher` e confirmação
específica da operadora, o ETag do ponteiro foi relido como
`b05c9a592fb5228df95663d07132992d`. O `put-object` condicional selecionou o
hotfix e retornou o novo ETag `f25663d61993b9a527fc8ac127aec701` com
SSE-S3/AES256. A leitura posterior confirmou exatamente a chave imutável
`runtime/frequenia-arm64-fb58666254fae4a08baa71b3b18bdc981919cdb92087874c0597c55504eab082.tar.gz`.
A EC2 foi consultada e permanece `stopped`, `t4g.small`, ARM64. Banco, plano,
stack e reconhecimento facial não foram alterados. As imagens anteriores
permanecem disponíveis para rollback.

### Validação técnica do hotfix no piloto — 25/10/2026

Com confirmação específica, o controlador iniciou a EC2 existente. O agente
SSM ficou `Online` e `frequenia.service` ficou `active`. A tag efetivamente
executada `frequenia:pilot` apresentou ID
`sha256:df86bf72bf07cfb9bedd9280a0a1442cfa65029aa0a391fc5363c7856e5ed537`,
igual ao config do pacote do hotfix, arquitetura ARM64/Linux. App, dispatcher,
worker, Caddy e ClamAV ficaram `running`, todos com zero reinícios. HTTPS
validou o certificado; `/health` e `/ready` responderam 200 após a janela de
inicialização.

Um diagnóstico executado dentro do app produziu somente indicadores booleanos:
referência do projeto esperado = 1, `sslmode=verify-full` = 1, CA legível = 1
e TLS do cliente libpq ativo = 1. O `pg_stat_ssl` observado por trás do pooler
retornou 0 e não foi usado como prova da conexão cliente; nenhuma URL, host,
credencial, linha pessoal, foto ou embedding foi exibido. Não houve migration,
teste autenticado ou ativação facial. O perfil publicador não possui
`ssm:SendCommand`; a inspeção foi feita por sessão SSM autorizada, encerrada em
seguida. O controlador recebeu `stop`, a EC2 foi confirmada em `stopped`, sem
trava de custo, com 48.156 de 144.000 segundos usados. A imagem anterior segue
preservada para rollback.

Após a validação técnica, a `Equipe FrequenIA` aprovou a decisão biométrica
v1.0 limitada aos desenvolvedores adultos voluntários. Foi preparado um
operador local de credenciais privadas para criar, em ações separadas, a
política, o perfil e consultar readiness por meio das APIs autenticadas do
piloto. O script não foi executado; nenhuma política ou perfil foi criado no
banco nesta preparação. O parser PowerShell e 12 testes de infraestrutura
passaram.

### Correção de rollback biométrico preparada — 25/10/2026

Antes de gravar a primeira política real, a revisão do fluxo encontrou que as
APIs criavam política e perfil sem `vigencia_fim` e não ofereciam desativação
administrativa do perfil. Como a política aprovada é append-only, a gravação
foi interrompida sem criar linha remota. A EC2, iniciada apenas para preparar a
operação, mostrou `health=200` e `ready=200` internamente; houve atraso de DNS,
mas o registro público já correspondia ao IP atual em comparação booleana. A
sessão foi encerrada e a EC2 confirmada em `stopped`.

Localmente, política e perfil passaram a exigir vigência encerrada em
25/10/2027. Foi adicionada uma rota autenticada `administrador`/`rh` que
desativa o perfil ativo em transação, com lock e auditoria, permitindo rollback
sem SQL manual. O operador privado ganhou a ação `disable`. Passaram 25 testes
de governança, 12 de infraestrutura, os parsers Python/PowerShell e um smoke
ARM64 sem rede.

A imagem incremental foi construída sobre o hotfix já validado e empacotada
com a tag única `frequenia:pilot`. O arquivo local
`infra/aws/dist/frequenia-arm64-pilot-20261025-biometric-rollback.tar.gz` tem
920.675.134 bytes, SHA-256
`d548ec844d4965ec1fa663bfb3fdad8cd7e945679940a6a426c4c4f04b4540cf`
e config `sha256:76f97392…e7de9c`. A leitura integral do tar gzip concluiu com
31 entradas. Nenhum upload, ponteiro, política, perfil ou dado biométrico foi
alterado nesta preparação.

Com confirmação específica posterior, o pacote foi enviado à chave privada
imutável
`runtime/frequenia-arm64-d548ec844d4965ec1fa663bfb3fdad8cd7e945679940a6a426c4c4f04b4540cf.tar.gz`.
O `head-object` confirmou 920.675.134 bytes, SSE-S3/AES256 e metadado SHA-256
igual ao hash local. O ETag multipart
`735aaa1d9ebb22903367a6aebf39f3ae-110` não foi usado como hash independente.
O ponteiro continua na imagem anterior; EC2, banco, política e perfil não foram
alterados. O pacote intermediário segue preservado até confirmação específica
de eventual exclusão.

Após confirmação específica, o ponteiro foi atualizado condicionalmente pelo
ETag anterior `f25663d61993b9a527fc8ac127aec701`. A operação retornou o novo
ETag `5fd35ec196ea260749f2d0785e30ce5c`; a leitura posterior confirmou exatamente
a chave `runtime/frequenia-arm64-d548ec844d4965ec1fa663bfb3fdad8cd7e945679940a6a426c4c4f04b4540cf.tar.gz`.
A EC2 foi reconfirmada em `stopped`. Não houve escrita no banco, criação de
política/perfil ou ativação facial. Imagens anteriores foram preservadas.

### Validação da imagem com rollback — 25/10/2026

Com confirmação específica, o controlador iniciou a EC2 e o piloto carregou a
tag `frequenia:pilot` com ID
`sha256:76f9739281ebc8e7eb9b1e1b2db79aa336bce9c94980c594fb703e656ae7de9c`,
igual ao config do pacote selecionado, ARM64/Linux. App, dispatcher, worker,
Caddy e ClamAV ficaram ativos, todos com zero reinícios. `/health` e `/ready`
responderam 200 interna e publicamente; o certificado HTTPS foi validado. A
nova rota de desativação respondeu 401 sem autenticação, comprovando existência
e proteção sem executar mutação. Não houve política, perfil ou teste facial.

A sessão SSM foi encerrada; o controlador recebeu `stop` e confirmou a EC2 em
`stopped`, sem trava de custo, com 48.369 de 144.000 segundos usados. A imagem
com rollback está tecnicamente publicada e validada, mas a governança remota e
o uso facial continuam pendentes de operações autorizadas separadamente.

Na etapa local seguinte, o ciclo completo de governança e rollback passou em
15/15 testes de integração contra PostgreSQL descartável com dados sintéticos.
Foram validados política e perfil com vigência final, prontidão positiva,
desativação autenticada e prontidão negativa após rollback. O container de
teste foi removido; backup, Supabase e recursos AWS permaneceram inalterados.

### Emenda local de retenção v1.1 — 25/10/2026

A controladora aprovou a primeira vigência da política e do perfil até
24/11/2026 e prazo máximo de 1.825 dias desde o cadastro para embeddings. A decisão preserva o
escopo 1:1 dos desenvolvedores adultos voluntários, sem treinamento, com
revisão em 30 dias e eliminação antecipada. Sem nova versão, o reconhecimento
para de forma segura no vencimento. O prazo das
fotos antigas não foi ampliado. O aviso e o aceite individual passam à versão
1.1 antes do uso real.

O operador autenticado agora prepara `pilot-dev-1.1.0`, retenção `1825` e
vigência final em 24/11/2026. Passaram o parser PowerShell, 12/12 testes de
infraestrutura, 25/25 de governança e 15/15 de integração PostgreSQL contra
container descartável, posteriormente removido. A EC2 foi confirmada
`stopped`; nenhuma política, perfil ou linha pessoal foi criada ou consultada.

A configuração final de 30 dias foi revalidada localmente: 12/12 testes de
infraestrutura, 25/25 de governança, parser PowerShell e 15/15 integrações
PostgreSQL. O container sintético foi removido; não houve acesso ao Supabase.

Após confirmação específica e validação pública do piloto, a operadora criou a
política remota `pilot-dev-1.1.0` pelo fluxo autenticado privado. A única saída
compartilhada foi `policy_created=1` e `retention_days=1825`. A política vence
em 24/11/2026. Perfil, fotos, embeddings e reconhecimento não foram alterados.

Com nova confirmação específica, a operadora criou o perfil técnico
`pilot-dev-1.1.0`; a saída sanitizada confirmou `profile_created=1` e limiar
`0.68`. Política e perfil agora existem, ambos com vigência até 24/11/2026.
Readiness e teste facial real ainda dependem das etapas seguintes.

O readiness autenticado foi consultado sem dados pessoais e confirmou
`policy=1`, `profile=1` e `compatible=1`. A ativação técnica está completa; o
teste 1:1 com pessoa real continua condicionado à confirmação específica e ao
aceite v1.1 já declarado.

O teste real posterior, já com recadastro v1.1 autorizado, passou pela
verificação facial no APK e alcançou o motor de jornada. A marcação foi
corretamente bloqueada como `sem_jornada`, sem inventar tipo de ponto, e a
tentativa seguiu para análise. O facial 1:1 está operacional; a jornada do
vínculo permanece uma configuração independente antes de homologar o fluxo
completo de marcação.

### APK release 1.0.1+2 preparado — 25/10/2026

O APK anterior no S3 tem 54.383.094 bytes e permanece preservado na chave
versionada `apk/frequenia-1.0.0-pilot.1.apk`; o ponteiro `latest` ainda aponta
para esse mesmo objeto. Ambos usam SSE-S3/AES256. A versão antiga está assinada
com certificado Android Debug e não foi reutilizada.

Foi criada pela operadora uma chave release privada, ignorada pelo Git, com RSA
4096 e certificado `CN=Equipe FrequenIA, OU=Piloto, O=Equipe FrequenIA, C=BR`.
O novo APK foi compilado com ambiente `production`, base HTTPS fixa
`https://frequenia.duckdns.org`, applicationId `br.com.frequenia.app`, versão
`1.0.1`, versionCode `2`, minSdk `26` e targetSdk `36`. O APK tem 54.415.870
bytes, SHA-256
`9571378fa548d25d05faa3a49573486d3481c264a2d2b6479698c1140013e6a8` e
assinatura v2 válida com um signatário RSA 4096. Análise Flutter sem achados,
48/48 testes Flutter e 13/13 contratos de infraestrutura passaram. Nenhum APK
novo foi enviado ao S3 nesta preparação.

Com confirmação específica, o operador publicou o APK em
`apk/frequenia-1.0.1-pilot.2.apk`, publicou o checksum correspondente e
substituiu `apk/frequenia-latest.apk`. O comando concluiu com SHA-256
`9571378fa548d25d05faa3a49573486d3481c264a2d2b6479698c1140013e6a8` e
retornou o link público esperado. A chave antiga
`apk/frequenia-1.0.0-pilot.1.apk` não foi alterada. A verificação adicional por
novo download não executou porque o revisor automático de permissões atingiu o
limite de uso; isso não reverteu o upload concluído.

### Resultado funcional e encerramento — 25/10/2026

O APK publicado concluiu a verificação facial 1:1 e alcançou o motor de
jornada. A marcação não foi persistida porque o snapshot de 25/10/2026 estava
materializado como `sem_jornada`; sua imutabilidade foi preservada. A operadora
informou ter configurado escala temporária para 26/10/2026, mantendo pendente
somente a validação completa da marcação nessa data. A sessão foi encerrada e
o controlador confirmou a EC2 em `stopped`, sem trava de custo, com
52.557/144.000 segundos utilizados.

### Homologação facial ponta a ponta — 26/10/2026

Em nova sessão controlada, a instância existente ficou `running`, o certificado
HTTPS foi validado e `/health` e `/ready` retornaram `200`. Após confirmação
específica para o teste com biometria real previamente autorizada, a operadora
informou que o APK reconheceu o rosto e registrou o ponto corretamente na
jornada vigente. A evidência foi mantida sanitizada; nenhuma foto, embedding,
matrícula ou linha pessoal foi acessada ou registrada pelo assistente.

### Hotfix do quiosque pendente — 26/10/2026

O teste posterior do quiosque alcançou a API, mas recebeu o erro genérico de
registro. Sem ler logs brutos ou dados pessoais, a inspeção local encontrou
uma incompatibilidade determinística: o cursor real retorna o `id` por nome,
enquanto `_record_attempt` tentava acessá-lo pela posição zero. A correção em
`routes/kiosk.py` e o teste que reproduz `RealDictCursor` passaram em 7/7
contratos do quiosque e 3/3 testes de confiabilidade biométrica. O build ARM64
não concluiu porque o daemon Docker derrubou o disco WSL durante a cópia da
camada e, depois, a distribuição passou a falhar com `CreateInstance E_FAIL`.
Nenhum artefato foi enviado, o ponteiro não mudou e a EC2 foi confirmada em
`stopped`. A retomada exige reiniciar o Windows, validar o WSL e reconstruir a
imagem imutável antes de qualquer nova publicação autorizada.

### Pacote local do hotfix do quiosque — 13/11/2026

Após recuperar espaço na unidade Windows e remontar corretamente o disco WSL,
o hotfix foi reconstruído como uma camada mínima sobre a imagem imutável de
25/10/2026. O pacote local
`infra/aws/dist/frequenia-arm64-pilot-kiosk-hotfix-20261113-v2.tar.gz` tem
920.680.399 bytes e SHA-256
`be18f7265ff59d9df8ecc1f445612606d5453244607d1beb44a9eca3f6c36b47`.
O `gzip -t` integral passou; o manifesto contém somente a tag
`frequenia:pilot` e config
`sha256:50a7eee24a61267b95eee473598cf74b53cb604a18dfbc51cd43b79786772b59`,
ARM64/Linux. Os 7 testes do quiosque e 3 testes de confiabilidade biométrica
passaram. Nenhum upload, ponteiro, EC2, banco ou política foi alterado.

A publicação permaneceu bloqueada porque `aws login` retornou erro na página
de autorização tanto em `sa-east-1` quanto em `us-east-1`; a conexão AWS do
Codex também solicitou reautenticação. Não foi usada a sessão root como atalho.
O próximo passo é restaurar a permissão de login local do IAM restrito
`frequenia-publisher`, autenticar novamente e só então propor upload e troca de
ponteiro em confirmações separadas.

### Publicação e validação do hotfix do quiosque — 13/11/2026

A política `SignInLocalDevelopmentAccess` já estava anexada ao grupo do usuário
restrito; após a operadora renovar a credencial do console e concluir o fluxo
interativo, `sts get-caller-identity` confirmou o principal
`frequenia-publisher` na conta esperada. Nenhuma chave de acesso permanente foi
criada e a sessão root não foi usada para operar recursos.

Com confirmações específicas separadas, o pacote de SHA-256
`be18f7265ff59d9df8ecc1f445612606d5453244607d1beb44a9eca3f6c36b47`
foi enviado a uma chave imutável do bucket privado existente e o ponteiro
`runtime/current-image-key.txt` foi trocado condicionalmente pelo ETag. O
objeto remoto tem 920.680.399 bytes, SSE-S3/AES256 e metadado SHA-256 igual ao
hash local. A imagem anterior `d548ec84…540cf` foi preservada para rollback.

No primeiro boot controlado, o config efetivo
`sha256:50a7eee24a61267b95eee473598cf74b53cb604a18dfbc51cd43b79786772b59`
e a linha corrigida do quiosque foram confirmados no container. HTTPS,
`/health` e `/ready` passaram, mas a conexão PostgreSQL retornou de forma
sanitizada `ENOTFOUND tenant/user`; DNS, TCP e TLS `verify-full` estavam
corretos. A instância foi desligada e confirmada `stopped` enquanto a operadora
despausava o projeto Free do Supabase, sem alterar URL, banco ou plano.

No segundo boot, a conexão sanitizada retornou `db_connect=1`; app, worker,
dispatcher, Caddy e ClamAV ficaram ativos, e `/health` e `/ready` responderam
200. Após confirmação específica, uma desenvolvedora abrangida pelo aviso
v1.1 executou o reconhecimento facial 1:1 no quiosque e informou que ele
funcionou. Não foram acessados ou registrados neste relatório foto, embedding,
matrícula, identidade ou linha pessoal. A sessão SSM foi encerrada, o
controlador recebeu `stop`, a EC2 foi confirmada em `stopped` e o ponteiro
permaneceu no hotfix publicado.

