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
facial `sucesso/match` pode autorizar uma marcacao. O padrao e `120`; o cliente
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

Com Docker disponivel no PowerShell:

```powershell
docker build --tag frequenia-backend:local .
docker run --detach --name frequenia-backend-local --env-file .env --publish 5013:5000 frequenia-backend:local
```

Quando o Docker estiver disponivel somente no Ubuntu/WSL:

```powershell
wsl -d Ubuntu -- bash -lc "cd /mnt/c/CAMINHO/PARA/FrequenIA && docker build --tag frequenia-backend:local ."
wsl -d Ubuntu -- bash -lc "cd /mnt/c/CAMINHO/PARA/FrequenIA && docker run --detach --name frequenia-backend-local --env-file .env --publish 5013:5000 frequenia-backend:local"
```

Teste sem imprimir configuracao:

```powershell
(Invoke-WebRequest http://localhost:5013/health).StatusCode
```

O resultado esperado e HTTP `200`.

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
