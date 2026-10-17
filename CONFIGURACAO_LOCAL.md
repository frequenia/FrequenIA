# Configuracao local segura do FrequenIA

## Estrategia oficial

- `.env` e o unico arquivo local de configuracao do backend.
- `.env.example` e o modelo versionado, sem valores reais.
- O Docker recebe `.env` somente em runtime por `--env-file`.
- `.env`, `.env.*`, chaves privadas e arquivos locais de credenciais nao entram
  no Git nem no contexto da imagem Docker.

Arquivos como `.env.frequenia.local`, `DB_*`, `NEW_DB_*` e `NEW_DB_URL` nao
fazem parte do runtime atual. Esses nomes existem apenas em ferramentas
historicas de migracao das Fases 4F/4G e nao devem ser usados para iniciar o
backend.

## Pre-requisitos

- Git;
- Docker Desktop;
- WSL2 no Windows, quando usado pelo Docker;
- virtualizacao habilitada;
- acesso autorizado a credenciais validas de homologacao.

## Preparar a configuracao

No diretorio do projeto:

```powershell
Copy-Item .env.example .env
```

Preencha o `.env` localmente. Nao envie esse arquivo ao Git e nao coloque
segredos em comandos, Dockerfile, documentacao ou mensagens.

Obrigatorias para iniciar o Flask:

- `FLASK_SECRET_KEY`;
- `JWT_SECRET_KEY`.

Obrigatoria para login e APIs que consultam dados:

- `DATABASE_URL`.

Para comprovantes opcionais de correção, configure `ATTACHMENT_STORAGE_ROOT`
com um diretório privado, gravável pelo backend e fora do repositório, de
`static/` e de qualquer servidor web. O backend recusa uploads quando a
variável está vazia e nunca usa o nome enviado pelo usuário como caminho. Para
desenvolvimento, prefira um diretório temporário descartável; esta fase não
define nem provisiona armazenamento de produção.

Na Fase 27, `ATTACHMENT_STORAGE_PROVIDER=s3` seleciona o adaptador durável.
Configure somente no servidor `ATTACHMENT_S3_BUCKET`, `ATTACHMENT_S3_REGION` e,
para serviços compatíveis locais, `ATTACHMENT_S3_ENDPOINT_URL`. Credenciais vêm
da cadeia padrão do SDK/role; não existem variáveis de access key no contrato.
Produção rejeita o provedor local e endpoints sem TLS. O scanner usa
`ATTACHMENT_SCANNER_PROVIDER=clamav`, `CLAMAV_HOST`, `CLAMAV_PORT` e timeout.
Scanners falsos só funcionam com `APP_ENV=test`. Retenção padrão: 90 dias para
substituídos/removidos e 30 dias para infectados.

Na Fase 28, use `ATTACHMENT_SCAN_MODE=async`,
`ATTACHMENT_QUEUE_PROVIDER=sqs` e `ATTACHMENT_QUEUE_URL`. Um endpoint SQS
compatível local é aceito somente em testes. Produção rejeita fila em memória e
modo síncrono. Execute o dispatcher com
`python tools/dispatch_attachment_scan_jobs.py --continuous` e o worker com
`python tools/run_attachment_scan_worker.py`; nenhum consumidor roda como
thread do Gunicorn. `CLAMAV_SIGNATURE_MAX_AGE_HOURS` controla o fail-closed de
assinaturas. S3 e SQS usam exclusivamente a cadeia padrão de credenciais.
`ATTACHMENT_DLQ_URL` identifica a DLQ apenas por configuração server-side para
o comando administrativo de redrive; ela nunca vem de payload ou parâmetro do
operador.

Na Fase 29, `CONTINUITY_RPO_SECONDS`, `CONTINUITY_RTO_SECONDS`,
`CONTINUITY_FREQUENCY_HOURS`, `CONTINUITY_BACKUP_RETENTION_DAYS`,
`CONTINUITY_EXERCISE_WINDOW_MINUTES` e `CONTINUITY_MAX_SET_BYTES` controlam
somente exercícios isolados. Os defaults locais não constituem SLO. Produção
permanece recusada enquanto `CONTINUITY_PRODUCTION_APPROVED` não estiver
formalmente aprovado e acompanhado por `CONTINUITY_APPROVAL_REFERENCE`.
Conjuntos devem ficar fora do repositório, `static/` e diretórios públicos.

Na Fase 30, o backend é a única autoridade sobre o tipo da próxima marcação.
`JOURNEY_DEFAULT_TIMEZONE` é usado apenas quando não existe turno aplicável;
`JOURNEY_OPEN_GRACE_HOURS` limita a busca de jornada anterior ainda aberta.
`JOURNEY_EARLY_TOLERANCE_MINUTES` e `JOURNEY_LATE_TOLERANCE_MINUTES` são
informativos e não calculam desconto, hora extra ou efeito trabalhista. Os
valores devem ser inteiros não negativos (a janela aberta deve ser positiva).
Mobile e quiosque não configuram empresa, funcionário, timezone ou tipo.

Na Fase 31, defina `BIOMETRIC_AWAY_POLICY` explicitamente como `bloquear`,
`revogar` ou `preservar`. A migration `026` deve seguir a `025`. Política
aprovada e perfil técnico ativo são dados versionados no PostgreSQL; não há
base legal, retenção ou fixture silenciosa padrão. Canal de atendimento,
referência jurídica, retenção e aprovação devem vir do controlador. Ausência ou
incompatibilidade bloqueia novas operações sensíveis sem apagar cadastros.

Configuracao geral:

- `APP_ENV`;
- `PORT`;
- `JWT_ACCESS_TOKEN_MINUTES`;
- `JWT_REFRESH_TOKEN_DAYS`;
- `PASSWORD_RESET_TOKEN_MINUTES`;
- `CORS_ALLOWED_ORIGINS`.

`FACE_VERIFICATION_MAX_COSINE_DISTANCE` define no servidor o limite da
comparacao ArcFace 1:1 por distancia cosseno. O valor inicial `0.68` corresponde
ao padrao do DeepFace 0.0.99 para ArcFace/cosseno. Esse valor nao e controlado
pelo cliente e deve ser calibrado com amostras controladas antes de qualquer
piloto com pessoas reais.

`FACIAL_ATTEMPT_MAX_AGE_SECONDS` define por quantos segundos uma tentativa
facial permanece válida nos fluxos biométricos legados. O padrão é `120`; o cliente
nao pode informar nem alterar essa janela.

`PASSWORD_RESET_TEST_KEY` e opcional e deve existir apenas em homologacao
controlada. A aplicacao recusa essa chave em producao.

O fluxo facial legado tambem utiliza:

- `CLOUDINARY_CLOUD_NAME`;
- `CLOUDINARY_API_KEY`;
- `CLOUDINARY_API_SECRET`.

Use segredos aleatorios e diferentes para Flask e JWT. Credenciais devem ser
entregues por um gerenciador de senhas ou cofre aprovado.

## Construir e executar

O fluxo recomendado sobe o backend, aguarda o health check e abre o Flutter no
primeiro emulador Android disponivel:

```powershell
.\iniciar_mobile.bat
```

O emulador recebe `BASE_URL=http://10.0.2.2:5013`. Para escolher um dispositivo
ou usar um celular fisico, informe os parametros ao launcher:

```powershell
.\iniciar_mobile.bat -DeviceId ID_DO_DISPOSITIVO
.\iniciar_mobile.bat -DeviceId ID_DO_CELULAR -BaseUrl http://IP_DA_MAQUINA:5013
```

O IP da maquina deve ser alcancavel pelo celular na mesma rede. O firewall deve
permitir a porta somente na rede privada autorizada. Para subir apenas o
backend ou consultar logs:

```powershell
docker compose up --build --detach
(Invoke-WebRequest http://localhost:5013/health).StatusCode
docker compose logs --tail 100 backend
```

O resultado esperado e HTTP `200`.

Para homologacao ou producao no Cloud Run, consulte `DEPLOY_CLOUD_RUN.md`. O
Flutter mobile e executado ou compilado separadamente com a URL HTTPS publicada.

## Executar em outro computador

1. Instale Git, Docker Desktop e WSL2 quando necessario.
2. Clone `https://github.com/frequenia/FrequenIA.git`.
3. Selecione a branch aprovada para homologacao.
4. Copie `.env.example` para `.env` no novo computador.
5. Receba as credenciais por canal seguro e preencha o arquivo localmente.
6. Execute o build, crie o container e valide `/health`.

Nunca envie `.env` pelo GitHub. Para equipes, prefira um cofre de segredos com
credenciais proprias e de privilegio minimo para cada ambiente.

## Rotacao obrigatoria apos exposicao

Devem ser rotacionados nos respectivos provedores:

- senha PostgreSQL/Supabase;
- segredo/API do Cloudinary;
- qualquer chave ou senha que tenha sido reutilizada em outro sistema.

Depois da rotacao, atualize somente o `.env` local. Nao preserve credenciais
antigas em arquivos paralelos.
Para busca de endereço e prévia de mapa da geofence, configure
`TOMTOM_API_KEY`. `TOMTOM_TIMEOUT_SECONDS` controla o timeout das chamadas
externas e assume 5 segundos. A chave fica apenas no backend; sem ela a
validação do perímetro continua funcionando, mas mapa e endereço ficam
indisponíveis.
