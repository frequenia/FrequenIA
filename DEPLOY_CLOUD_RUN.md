# Publicacao do FrequenIA no Cloud Run

O Cloud Run hospeda o Flask, a API e as paginas administrativas. O Flutter
continua sendo um aplicativo Android/iOS e recebe a URL HTTPS da API em tempo
de compilacao. Ele nao e executado dentro do container.

## Recursos e nomes adotados

- regiao: `southamerica-east1`;
- repositorio Artifact Registry: `frequenia`;
- servico Cloud Run: `frequenia-api`;
- service account de runtime: `frequenia-cloud-run`;
- imagem: `southamerica-east1-docker.pkg.dev/PROJECT_ID/frequenia/frequenia-api`.

O `cloudbuild.yaml` constroi a imagem, executa a suite unitaria dentro dela,
cria uma revisao sem trafego, associa a tag `candidate`, valida `/health` nessa
revisao e somente entao direciona o trafego para a revisao mais recente. A
configuracao usa Gen2, 2 CPUs, 4 GiB, concorrencia 1, timeout de 300 segundos,
minimo de uma e maximo de tres instancias.

## Preparacao unica do projeto GCP

Autentique o `gcloud`, selecione o projeto e habilite as APIs:

```powershell
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create frequenia --repository-format=docker --location=southamerica-east1 --description="Imagens do FrequenIA"
gcloud iam service-accounts create frequenia-cloud-run --display-name="FrequenIA Cloud Run"
```

Crie os segredos abaixo sem colocar valores em arquivos versionados ou na
linha de comando. O Console do Secret Manager ou `gcloud secrets versions add
NOME --data-file=-` permitem informar o valor pela entrada padrao.

| Segredo no Secret Manager | Variavel no container |
| --- | --- |
| `frequenia-database-url` | `DATABASE_URL` |
| `frequenia-flask-secret-key` | `FLASK_SECRET_KEY` |
| `frequenia-jwt-secret-key` | `JWT_SECRET_KEY` |
| `frequenia-cloudinary-cloud-name` | `CLOUDINARY_CLOUD_NAME` |
| `frequenia-cloudinary-api-key` | `CLOUDINARY_API_KEY` |
| `frequenia-cloudinary-api-secret` | `CLOUDINARY_API_SECRET` |
| `frequenia-emailjs-service-id` | `EMAILJS_SERVICE_ID` |
| `frequenia-emailjs-template-id` | `EMAILJS_TEMPLATE_ID` |
| `frequenia-emailjs-public-key` | `EMAILJS_PUBLIC_KEY` |
| `frequenia-emailjs-private-key` | `EMAILJS_PRIVATE_KEY` |

Mesmo uma integracao opcional deve possuir uma versao de segredo configurada;
use o valor aprovado para o ambiente, nunca um valor real no repositorio.

Conceda `roles/secretmanager.secretAccessor` a conta de runtime em cada um
desses segredos. A conta usada pelo Cloud Build precisa de:

- `roles/artifactregistry.writer` no repositorio `frequenia`;
- `roles/run.admin` no projeto;
- `roles/iam.serviceAccountUser` sobre `frequenia-cloud-run`.

Conceda essas permissoes ao service account efetivamente mostrado em
`gcloud builds get-default-service-account`, pois projetos novos podem usar uma
conta diferente da conta legada do Cloud Build.

## Banco antes do rollout

As migrations nao rodam no startup do container. Antes da primeira publicacao,
aplique no Supabase, pelo fluxo controlado do projeto, todas as migrations
pendentes em `supabase/migrations`, inclusive
`018_correction_manager_hr_workflow.sql`. Confirme no banco o historico de
migrations e execute a suite de integracao contra homologacao antes do rollout.

## Build e publicacao

Depois da preparacao e das migrations:

```powershell
gcloud builds submit --config cloudbuild.yaml .
gcloud run services describe frequenia-api --region southamerica-east1 --format="value(status.url)"
```

O primeiro comando constroi, envia, testa a revisao candidata e promove a
revisao somente se `/health` responder com sucesso. O segundo retorna a URL
HTTPS usada pelo aplicativo.

Execute ou gere o app Android com essa URL:

```powershell
Set-Location mobile
flutter run --dart-define=APP_ENV=production --dart-define=BASE_URL=https://URL_DO_CLOUD_RUN
flutter build appbundle --dart-define=APP_ENV=production --dart-define=BASE_URL=https://URL_DO_CLOUD_RUN
```

`APP_ENV=production` recusa HTTP, localhost, `127.0.0.1` e `10.0.2.2`.

## Verificacao, logs e rollback

```powershell
$serviceUrl = gcloud run services describe frequenia-api --region southamerica-east1 --format="value(status.url)"
(Invoke-WebRequest "$serviceUrl/health").StatusCode
gcloud run services logs read frequenia-api --region southamerica-east1 --limit 100
gcloud run revisions list --service frequenia-api --region southamerica-east1
```

Para rollback, escolha uma revisao conhecida na listagem e direcione todo o
trafego explicitamente:

```powershell
gcloud run services update-traffic frequenia-api --region southamerica-east1 --to-revisions REVISAO_ESTAVEL=100
```

Depois do health check, valide login, refresh, consulta de jornada, pagina
administrativa e um registro facial controlado. Monitore latencia, memoria e
erros de carregamento dos modelos nos logs antes de liberar o piloto.
