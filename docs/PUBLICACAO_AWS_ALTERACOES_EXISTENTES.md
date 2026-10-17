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

