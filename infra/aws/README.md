# Piloto FrequenIA na AWS com teto de US$ 5

Esta infraestrutura mantém o PostgreSQL no Supabase, executa o FrequenIA em uma
EC2 que fica desligada fora das sessões e publica o APK no S3. O runtime padrão
é `t4g.small` ARM64 com 2 GB de RAM, 30 GB gp3 e 4 GB de swap.

O controle possui três barreiras:

1. cada sessão vence após quatro horas;
2. `t4g.small` acumula no máximo 40 horas mensais e instâncias `medium`, 20;
3. um AWS Budget de US$ 5 para a EC2 em 80% e bloqueia a operação em 100%.

O AWS Budgets não é instantâneo. A atualização financeira pode atrasar várias
horas; por isso o watchdog de cinco minutos e o contador de tempo são as
barreiras principais. No Free Plan, a própria conta impede cobrança além dos
créditos, mas fecha após seis meses ou quando os créditos terminarem.

## Componentes

- `bootstrap.yaml`: bucket regional de artefatos; somente `apk/` fica público
  na região de São Paulo.
- `runtime.template.yaml`: VPC pública mínima, EC2, DynamoDB, controle de sessão,
  watchdog e alertas regionais.
- `billing.template.yaml`: orçamento global em `us-east-1` e funções de parada e
  bloqueio.
- `Dockerfile.arm64`: imagem ARM64 com ArcFace e Fasnet pré-carregados.
- `scripts/build-arm64.ps1`: constrói, inventaria, exporta e compacta a imagem.
- `scripts/deploy.ps1`: empacota e publica as três stacks.
- `scripts/pilot-session.ps1`: abre, renova, encerra e consulta uma sessão.
- `scripts/upload-apk.ps1`: publica APK versionado, `latest` e SHA-256.
- `scripts/unlock-cost.ps1`: remove a trava somente em mês UTC posterior.

## Pré-requisitos

1. Criar uma conta AWS nova no Free Plan e não vinculá-la a AWS Organizations.
2. Instalar AWS CLI v2, Docker Desktop com Buildx, Python 3.10+ e `cfn-lint`.
3. Autenticar o AWS CLI com uma identidade administrativa temporária e MFA.
4. Reservar gratuitamente um subdomínio no DuckDNS.
5. Confirmar que `sa-east-1` está habilitada na conta.

Nunca coloque chaves ou tokens no repositório. Copie
`infra/aws/runtime.env.example` para `.env.aws.local`, preencha localmente e
guarde o token DuckDNS em `.secrets/duckdns-token.txt`. Ambos os caminhos já
são ignorados pelo Git.

O arquivo de ambiente deve manter `APP_ENV=production`, `PORT=5000`, a conexão
TLS do Supabase e segredos Flask/JWT distintos. Ajuste `CORS_ALLOWED_ORIGINS`
para `https://SUBDOMINIO.duckdns.org`.

## Construção e validação ARM64

Execute na raiz do projeto:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
./infra/aws/scripts/build-arm64.ps1 -OutputPath infra/aws/dist/frequenia-arm64-CANDIDATO.tar.gz
```

O script exige um caminho de saída novo para preservar o artefato anterior. Ele
confere a arquitetura `arm64`, a presença das migrations até `026`, dos serviços
e dos comandos de dispatcher/worker, além da ausência de arquivos proibidos em
`/app`. A suíte backend é executada no checkout antes do build; não é embutida na
imagem de runtime. Em host sem emulação ARM64, a execução da imagem deve ser
validada na EC2 do piloto antes de considerar a publicação homologada. Registre
o SHA-256 do arquivo e o digest apresentados pelo script.

Antes de liberar o piloto, execute na EC2 pelo Session Manager os testes reais:

- três cadastros biométricos completos;
- vinte reconhecimentos sequenciais;
- duas marcações simultâneas;
- confirmação de ausência de OOM/restarts;
- p95 de reconhecimento de até 30 segundos.

Se ARM64 falhar apenas por biblioteca, publique uma imagem x86 equivalente e
implante `t3.small`. Se a memória falhar, use `t4g.medium` e mantenha o limite
mensal de 20 horas.

## Implantação

O comando abaixo cria recursos AWS. Confirme antes o saldo de créditos e o Free
Plan no console de faturamento.

```powershell
./infra/aws/scripts/deploy.ps1 `
  -NotificationEmail voce@empresa.com `
  -DuckDnsSubdomain frequenia-piloto `
  -DuckDnsTokenFile .secrets/duckdns-token.txt `
  -RuntimeEnvFile .env.aws.local `
  -ContainerArchivePath infra/aws/dist/frequenia-arm64.tar.gz
```

O script:

1. valida AWS CLI v2 e identidade;
2. cria buckets regionais criptografados;
3. grava os dois parâmetros como `SecureString`, sem ler seus valores;
4. envia a imagem privada para S3;
5. empacota e valida as Lambdas;
6. publica o runtime em `sa-east-1`;
7. publica o orçamento em `us-east-1`.

Confirme os três e-mails SNS recebidos. Sem essa confirmação, os desligamentos
continuam funcionando, mas os avisos por e-mail não chegam.

## Operação

```powershell
# Abre uma nova janela de quatro horas e inicia a EC2
./infra/aws/scripts/pilot-session.ps1 -Action start

# Renova por mais quatro horas
./infra/aws/scripts/pilot-session.ps1 -Action renew

# Consulta estado, prazo, horas e trava
./infra/aws/scripts/pilot-session.ps1 -Action status

# Encerra antes do prazo
./infra/aws/scripts/pilot-session.ps1 -Action stop
```

O uso direto de `StartInstances` não abre nova sessão. Se o prazo anterior já
venceu, o watchdog desliga a máquina em até cinco minutos.

## Publicação do APK

O APK deve ser release assinado com uma chave própria do piloto e compilado com:

```powershell
flutter build apk --release `
  --dart-define=APP_ENV=production `
  --dart-define=BASE_URL=https://frequenia-piloto.duckdns.org
```

Depois publique:

```powershell
./infra/aws/scripts/upload-apk.ps1 `
  -ApkPath mobile/build/app/outputs/flutter-apk/app-release.apk `
  -Version 1.0.0
```

O bucket permite leitura pública somente em `apk/`; listagem, artefatos Lambda,
imagem Docker e parâmetros permanecem privados.

## Desbloqueio no mês seguinte

O bloqueio financeiro não se remove automaticamente. Em um mês UTC posterior:

```powershell
./infra/aws/scripts/unlock-cost.ps1 -ConfirmUnlock
```

O script recusa a remoção durante o mesmo mês do bloqueio. A identidade que o
executa precisa ser administrativa; a role operacional não consegue remover a
própria trava.

## Verificação local

```powershell
python -m unittest discover -s infra/aws/tests -p 'test_*.py'
cfn-lint --regions sa-east-1 infra/aws/bootstrap.yaml infra/aws/runtime.template.yaml
cfn-lint --regions us-east-1 infra/aws/bootstrap.yaml infra/aws/billing.template.yaml
```

Depois do empacotamento, `deploy.ps1` também executa
`cloudformation validate-template` em cada região.

## Segurança e custo

- Não existe SSH público; administração usa AWS Systems Manager Session Manager.
- CPU burst fica em modo `standard`, evitando cobrança de créditos excedentes.
- Não há Elastic IP, NAT Gateway, load balancer, RDS, ECR ou snapshots.
- O bucket não mantém versionamento para evitar cópias cobradas; artefatos Lambda
  temporários expiram após sete dias.
- Os tópicos do orçamento não usam uma chave KMS própria: ela custaria cerca de
  US$ 1/mês e as mensagens carregam apenas estado financeiro, sem dados pessoais.
- Parar a EC2 não remove EBS ou S3. Esses recursos só devem ser apagados
  manualmente depois de preservar o que ainda for necessário.

