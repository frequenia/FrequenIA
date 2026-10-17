# FrequenIA

FrequenIA é uma aplicação Flask/PostgreSQL com interface web e aplicativo
Flutter para gestão de jornada e registro de ponto. O registro facial, as
ocorrências automáticas e as solicitações humanas de correção possuem fluxos
separados.

## Arquitetura do workflow de correções

- `routes/occurrences.py`: contratos HTTP pessoais e de gestão. A empresa, o
  usuário e o funcionário são obtidos exclusivamente da sessão autenticada.
- `services/correction_workflow.py`: política de estados, autorização por
  papel/escopo, transação, `SELECT ... FOR UPDATE`, auditoria e notificações.
- `services/management_scope.py`: isolamento de gestor por unidade/equipe;
  RH e administrador permanecem limitados à empresa da sessão.
- `services/effective_timekeeping.py`: visão imutável que combina marcações
  confirmadas e somente correções aprovadas. A tabela `marcacoes` não é
  atualizada pela aprovação.
- `routes/timekeeping.py`: consulta e exportações CSV/PDF/DOCX alimentadas pela
  mesma visão efetiva.
- `supabase/migrations/018_correction_manager_hr_workflow.sql`: estados finais,
  migração dos estados legados, índices e contrato de decisão.
- `services/correction_attachments.py`: validação de PDF/JPEG/PNG, autorização,
  auditoria, compensação e limite de um comprovante ativo por solicitação.
- `services/correction_attachment_storage.py`: interface local privada do
  piloto, configurada explicitamente e baseada apenas em chaves UUID do servidor.
- `supabase/migrations/021_correction_private_attachments.sql`: metadados
  privados e históricos do comprovante, sem binário no PostgreSQL.
- `services/attachment_outbox.py` e `services/attachment_worker.py`: publicação
  pós-commit e consumo idempotente via SQS/DLQ, sempre fail-closed.
- `services/attachment_reconciliation.py`: reconciliação paginada e dry-run.
- `supabase/migrations/023_attachment_scan_outbox.sql`: outbox transacional.
- `supabase/migrations/024_continuity_backup_chaos.sql`: evidências sanitizadas
  de continuidade e outbox recuperável da tag `purge-eligible`.
- `services/daily_journey.py`: motor único que resolve escala/turno, cria o
  snapshot diário e decide o próximo evento usando o relógio do PostgreSQL.
- `supabase/migrations/025_daily_journey_engine.sql`: escalas por data,
  snapshots imutáveis, eventos esperados e tentativas fora da sequência.
- `supabase/migrations/026_biometric_governance_lifecycle.sql`: política
  biométrica e perfil técnico versionados, hold, eliminação verificável e
  histórico append-only, sem inventar base legal ou prazo jurídico.

Estados oficiais: `pendente_gestor`, `encaminhada_rh`, `aprovada`, `rejeitada`
e `cancelada`. Estados finais não reabrem.

## Pré-requisitos

- Python 3.10+ e dependências de `requirements.txt`;
- PostgreSQL 16 com `pgcrypto` e `vector` (pgvector);
- Flutter já instalado para validar `mobile/`;
- Docker é opcional, mas recomendado para a homologação descartável.

Não use banco de produção nos comandos de teste. A suíte da Fase 25 rejeita
hosts remotos e exige o database local chamado `frequenia_phase25_test`.

## Configuração

Copie `.env.example` para um arquivo local ignorado pelo Git e substitua os
placeholders. Nunca versione o arquivo preenchido. Os nomes oficiais para os
serviços externos são:

- EmailJS: `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY`,
  `EMAILJS_PRIVATE_KEY` (opcional) e `EMAILJS_TIMEOUT_SECONDS`;
- TomTom: `TOMTOM_API_KEY` e `TOMTOM_TIMEOUT_SECONDS`.

Para comprovantes, `ATTACHMENT_STORAGE_ROOT` deve apontar para diretório
privado fora do repositório e de `static/`. Sem a variável, uploads e downloads
falham de forma segura com indisponibilidade; solicitações sem anexo continuam
válidas. Não use nomes enviados pelo usuário, URLs públicas ou diretórios
servidos pelo Flask.

As validações de segredo, CORS e tempos limite continuam ativas. Para iniciar
o backend localmente, configure ao menos `DATABASE_URL`, `FLASK_SECRET_KEY` e
`JWT_SECRET_KEY` com valores distintos e seguros e execute:

```powershell
python app.py
```

## Testes backend

### Descoberta padrão / testes unitários

Sem opt-in de integração, os testes PostgreSQL aparecem como `skip` explícito
e nenhum `.env` é consultado para decidir o banco de homologação:

```powershell
Remove-Item Env:PHASE25_TEST_DATABASE_URL -ErrorAction SilentlyContinue
python -m unittest discover -s tests -p "test_*.py" -v
```

### Integração PostgreSQL das Fases 25 e 26

Exemplo com contêiner efêmero e credencial exclusivamente local de teste:

```powershell
docker run --rm -d --name frequenia-phase25-postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=phase25_test_only `
  -e POSTGRES_DB=frequenia_phase25_test `
  -p 127.0.0.1:55435:5432 `
  pgvector/pgvector:pg16

$env:PHASE25_TEST_DATABASE_URL = `
  "postgresql://postgres:phase25_test_only@127.0.0.1:55435/frequenia_phase25_test"

python -m unittest discover -s tests `
  -p "test_phase25_postgres_integration.py" -v

$attachmentRoot = Join-Path ([System.IO.Path]::GetTempPath()) `
  ("frequenia-attachments-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $attachmentRoot | Out-Null
$env:ATTACHMENT_STORAGE_ROOT = $attachmentRoot
python -m unittest discover -s tests `
  -p "test_phase26_postgres_attachments.py" -v

docker rm -f frequenia-phase25-postgres
Remove-Item -LiteralPath $attachmentRoot -Recurse -Force
Remove-Item Env:ATTACHMENT_STORAGE_ROOT
Remove-Item Env:PHASE25_TEST_DATABASE_URL
```

A suíte apaga e recria os schemas do database informado. A Fase 25 valida a
`018` isoladamente e roda o workflow contra o schema atual. A Fase 26 aplica
`001`–`020`, preserva uma correção representativa ao aplicar `021`, repete
`001`–`021` em base limpa e exercita os anexos, compensação e concorrência com
duas conexões reais.

### Matriz de migrations

| Faixa | Responsabilidade validada |
|---|---|
| `001`–`017` | schema histórico, pgcrypto/pgvector e pré-condições do workflow |
| `018` | workflow Gestor → RH, estados, auditoria e visão efetiva |
| `019`–`020` | migrations incrementais já presentes no schema atual |
| `021` | metadados privados e históricos do comprovante opcional |
| `022` | quarentena, estados de segurança, retenção e trilha de purga |
| `023` | outbox transacional e controle idempotente da varredura assíncrona |
| `024` | exercícios de continuidade, histórico append-only e tagging pós-commit |
| `025` | escala/folga por data, snapshot diário e eventos esperados imutáveis |

O comando usado pela CI para uma instalação limpa equivalente é:

```powershell
$env:PHASE26_TEST_DATABASE_URL = $env:PHASE25_TEST_DATABASE_URL
python tools/apply_test_migrations.py
Remove-Item Env:PHASE26_TEST_DATABASE_URL
```

## Aplicar e verificar a migration 018

Em homologação autorizada, aplique as migrations em ordem e interrompa no
primeiro erro. O exemplo abaixo não inclui credenciais; a URL deve vir de um
segredo do ambiente:

```powershell
1..18 | ForEach-Object {
  $migration = Get-ChildItem supabase/migrations -Filter ("{0:D3}_*.sql" -f $_)
  if ($migration.Count -ne 1) { throw "Migration ausente ou duplicada: $_" }
  psql "$env:HOMOLOGATION_DATABASE_URL" -v ON_ERROR_STOP=1 -f $migration.FullName
}
```

Verificação mínima após a `018`:

```sql
select estado, count(*) from correcoes group by estado order by estado;
select conname, pg_get_constraintdef(oid)
from pg_constraint where conrelid = 'public.correcoes'::regclass;
select indexname, indexdef
from pg_indexes where schemaname = 'public' and tablename = 'correcoes';
```

Os estados devem pertencer ao conjunto oficial, a constraint
`correcoes_decisao_estado_check` deve permitir aprovação sem observação e
continuar exigindo justificativa para rejeição, e os índices
`correcoes_empresa_estado_data_idx` e
`correcoes_aprovadas_marcacao_operacao_unique` devem existir.

## Aplicar e verificar as migrations 021–025

Em banco descartável ou homologação explicitamente autorizada, aplique todas
as migrations em ordem, incluindo `021`, `022`, `023`, `024` e `025`. Para upgrade, faça primeiro um
snapshot/backup conforme a política do ambiente; nenhum comando deste projeto
acessa produção automaticamente.

```sql
select conname, pg_get_constraintdef(oid)
from pg_constraint where conrelid = 'public.anexos_correcao'::regclass;
select indexname, indexdef
from pg_indexes where schemaname = 'public' and tablename = 'anexos_correcao';
```

Devem existir FKs compostas de tenant, checks de MIME/tamanho/SHA/estado, o
índice `anexos_correcao_empresa_correcao_idx` e a unicidade parcial
`anexos_correcao_ativo_unique`.

## Flutter

Em `mobile/`:

```powershell
flutter analyze
flutter test
```

O aplicativo mantém a navegação existente e apresenta: “Pendente com gestor”,
“Encaminhada ao RH”, “Aprovada”, “Rejeitada” e “Cancelada”. A tela pessoal
permite escolher, mostrar, substituir e remover o comprovante apenas enquanto
o backend autorizar.

## CI

`.github/workflows/phase26-quality.yml` executa, em jobs separados, backend com
`pgvector/pgvector:pg16` descartável e Flutter. As actions são fixadas por
versão principal (`@vN`); atualizações de major devem passar por revisão e por
esta mesma matriz antes de serem aceitas. A CI usa somente credenciais locais
descartáveis definidas no workflow, não carrega `.env` e não referencia secrets
de produção. O secret scanning existente permanece independente e ativo.

A Fase 27 acrescenta um servidor S3 compatível (Moto) e ClamAV descartáveis com health
checks. A integração explícita é executada com:

```powershell
$env:PHASE27_TEST_DATABASE_URL = "postgresql://postgres:DESCARTAVEL@127.0.0.1:55435/frequenia_phase25_test"
$env:PHASE27_S3_ENDPOINT_URL = "http://127.0.0.1:9000"
$env:PHASE27_CLAMAV_HOST = "127.0.0.1"
python -m unittest discover -s tests -p "test_phase27_postgres_integration.py" -v
```

A Fase 28 usa o mesmo Moto como SQS compatível e adiciona a suíte explícita:

```powershell
$env:PHASE28_TEST_DATABASE_URL = "postgresql://postgres:DESCARTAVEL@127.0.0.1:55435/frequenia_phase25_test"
$env:PHASE28_SQS_ENDPOINT_URL = "http://127.0.0.1:9000"
$env:AWS_ACCESS_KEY_ID = "phase28-local"
$env:AWS_SECRET_ACCESS_KEY = "phase28-local-only"
$env:AWS_DEFAULT_REGION = "us-east-1"
python -m unittest discover -s tests -p "test_phase28_postgres_integration.py" -v
```

Essas credenciais são deliberadamente descartáveis e válidas apenas para o
emulador local; não correspondem a uma conta AWS. Remova-as da sessão após o
teste. A CI define equivalentes no próprio job e não consome GitHub Secrets.

O template `infra/aws/attachments.template.yaml` mantém S3 como rede de
segurança, nunca como autoridade de retenção: multipart incompleto expira em
7 dias e somente objetos marcados depois da decisão persistida no PostgreSQL
podem expirar, após margem configurável. O versionamento do bucket permanece
conscientemente desabilitado nesta fase para não criar versões que escapem da
purga auditada. O risco residual de exclusão acidental é compensado por chaves
opacas imutáveis, retenção do recurso CloudFormation, checksum obrigatório,
reconciliação dry-run e exercício de restauração descartável. Uma decisão de
backup/versionamento corporativo permanece para fase futura.

SQS e S3 usam criptografia gerenciada pelo serviço. Uma CMK paga não é criada
sem requisito formal de compliance. Nenhuma assinatura SNS é criada: o ARN de
um tópico existente pode ser fornecido posteriormente por operação autorizada.

O upload grava anexo e outbox na mesma transação. Publique com
`python tools/dispatch_attachment_scan_jobs.py` e processe com
`python tools/run_attachment_scan_worker.py --once` para uma rodada. O comando
`python tools/reconcile_correction_attachments.py --company-id UUID` é somente
leitura; reparo exige `--repair requeue-missing-job --execute`.

O comando `python tools/purge_correction_attachments.py` é dry-run. Remoções
exigem `--execute`; lote é limitado por `--batch-size`. O objeto é removido,
mas metadados e auditoria permanecem.

### Continuidade da Fase 29

Os comandos abaixo planejam por padrão. `--execute` é aceito apenas com
origem/destino descartáveis, fora do repositório e nunca em produção:

```powershell
python tools/prepare_continuity_backup.py --destination C:\Temp\frequenia-set `
  --artifact C:\Temp\synthetic.dump --component postgresql
python tools/export_test_postgres.py --target C:\Temp\synthetic.dump
python tools/verify_continuity_backup.py --source C:\Temp\frequenia-set
python tools/restore_continuity_backup.py --source C:\Temp\frequenia-set `
  --destination C:\Temp\frequenia-restore
python tools/tag_purge_eligible.py --batch-size 100
python tools/redrive_attachment_dlq.py --batch-size 10
```

Para mutar recursos descartáveis, repita com `--execute`; exportação lê a URL
somente de `PHASE29_SOURCE_DATABASE_URL`. Redrive lê a DLQ somente de
`ATTACHMENT_DLQ_URL`, exige `--authorized` e `--reason`, e preserva a mensagem
de origem até commit e confirmação.

RPO/RTO locais são parâmetros de exercício, não compromissos corporativos.
Produção permanece `aprovacao_corporativa_pendente` até que
`CONTINUITY_PRODUCTION_APPROVED=true` tenha uma referência formal aprovada.
Backups, dumps, manifestos preenchidos e evidências locais não entram no Git.

### Motor de jornada da Fase 30

O endpoint pessoal `GET /api/marcacoes/proxima` deriva empresa e funcionário
da autenticação e retorna a jornada operacional e o próximo evento. Mobile e
quiosque não enviam mais `tipo`; um valor legado divergente é enviado para
análise e nunca ganha autoridade. A ordem é calculada a partir da escala ativa
da data, depois da atribuição de turno vigente e, por fim, `sem_jornada`.

Escalas/folgas por data usam os endpoints administrativos em
`/api/admin/funcionarios/<uuid>/escalas`; gestor consulta apenas seu escopo e
RH/admin da empresa podem criar ou cancelar regra futura. Jornada já
materializada é imutável. Horários civis inexistentes ou ambíguos por mudança
de offset falham fechados, e a visão efetiva continua sendo usada para avançar
a sequência sem alterar a marcação original.

Integração PostgreSQL dedicada:

```powershell
$env:PHASE30_TEST_DATABASE_URL = `
  "postgresql://postgres:DESCARTAVEL@127.0.0.1:55435/frequenia_phase25_test"
python -m unittest discover -s tests `
  -p "test_phase30_postgres_integration.py" -v
Remove-Item Env:PHASE30_TEST_DATABASE_URL
```

## Checklist de homologação do piloto

- [ ] migrations `001`–`025` aplicadas em PostgreSQL/pgvector descartável limpo;
- [ ] upgrade representativo `001`–`024` + `025` preserva turnos, atribuições e marcações;
- [ ] upgrade com estados legados validado;
- [ ] constraints, FKs e índices da correção conferidos;
- [ ] 30 cenários PostgreSQL e concorrência aprovados;
- [ ] anexo PDF/JPEG/PNG, limite, assinatura e headers de download validados;
- [ ] autorização do solicitante, gestor, RH/admin e cross-tenant validada;
- [ ] compensação objeto/metadado e unicidade concorrente validadas;
- [ ] duplicação, fora de ordem, visibility timeout, retry e DLQ validados;
- [ ] reconciliação dry-run e restauração descartável aprovadas;
- [ ] alarmes, lifecycle e runbooks validados sem provisionamento;
- [ ] workflow de CI validado localmente e run remoto conferido no GitHub;
- [ ] descoberta padrão sem falhas/import errors e integração ausente em skip;
- [ ] `flutter analyze` sem issues;
- [ ] `flutter test` aprovado;
- [ ] motor resolve múltiplos períodos, virada de dia, escala, folga e ausência de jornada;
- [ ] duas materializações e duas marcações concorrentes preservam unicidade;
- [ ] mobile e quiosque não enviam nem oferecem escolha autoritativa de tipo;
- [ ] UI web e Flutter conferidos com os cinco rótulos oficiais;
- [ ] marcação original comparada antes/depois sem alteração;
- [ ] visão efetiva e exportações comparadas;
- [ ] não enumeração, cross-tenant e escopo do gestor confirmados;
- [ ] auditoria, timestamps do banco e notificações conferidos;
- [ ] workflow `falha_facial` validado sem mistura com correções;
- [ ] logs revisados sem CPF, imagem, embedding, segredo ou URL privada;
- [ ] nenhuma ação executada em produção.

## Limitações conhecidas

- o adaptador S3 compatível está implementado, mas nenhum bucket, role ou serviço
  de produção foi provisionado nesta fase;
- atualização efetiva das assinaturas ClamAV e resposta aos alarmes continuam
  responsabilidade operacional separada da aplicação;
- a promoção em S3 usa cópia e remoção coordenadas pelo estado transacional do
  PostgreSQL, pois o protocolo S3 não oferece rename atômico;
- não há notificação push;
- XLSX, espelho de ponto, relatórios consolidados, escalas mensais e troca de
  turno permanecem fora deste escopo;
- homologação externa depende de ambiente e autorização explícitos;
- o exercício desta fase é continuidade descartável, não backup/DR corporativo;
  LGPD operacional completa permanece pendente.

Os relatórios e matrizes estão em `docs/FASE_25_HOMOLOGACAO.md`,
`docs/FASE_26_ANEXOS_CI.md`,
`docs/FASE_27_STORAGE_ANTIMALWARE_RETENCAO.md` e
`docs/FASE_28_FILA_OBSERVABILIDADE_CONTINUIDADE.md`,
`docs/FASE_29_CONTINUIDADE_CAOS_BACKUP.md` e
`docs/FASE_30_MOTOR_JORNADA_MARCACAO_ESPERADA.md`.

## Guia de estilo FrequenIA

### Paleta de cores

- **FrequenIA Blue** — `--color-primary`, `#0f5c8c`: botões principais,
  ícones e textos de destaque;
- **Dark Blue** — `--color-primary-dark`, `#0c4a70`: hover e elementos
  interativos;
- **White** — `--color-white`, `#ffffff`: fundos de cards e texto em botões;
- **Light Gray** — `--color-bg-light`, `#f0f2f5`: fundo da página;
- **Medium Gray** — `--color-border`, `#e5e7eb`: bordas, divisores e tabelas;
- **Dark Gray** — `--color-text-dark`, `#222222`: títulos e textos;
- **Input BG** — `--color-input-bg`, `#fafbfc`: fundo de inputs.

### Tipografia

A fonte principal é Montserrat.

- título de página: `28px`, peso `700`;
- título de seção: `20px`, peso `600`;
- subtítulo/card: `18px`, peso `600`;
- label e cabeçalho de tabela: `18px`, peso `600`, uppercase;
- corpo: `18px`, peso `400`;
- destaque: `18px`, peso `700`, cor primária;
- badges: `18px`, peso `600`, cor primária escura.

### Componentes

- cards: padding `22px 24px`, raio `10px`, sombra
  `0 2px 10px rgba(0, 0, 0, 0.07)`;
- botões: altura `40px`, fonte `18px`, raio `7px`, peso `600`;
- inputs/selects: altura `40px`, fonte `18px`, borda
  `1.5px solid #dde1e7`, fundo `#fafbfc`;
- tabelas: fonte `18px`, cabeçalho `10px 14px`, célula `13px 14px`, hover
  `#fafbfc`.

## Fase 31 — governança biométrica

Cadastro e verificação facial 1:1 exigem política aprovada e perfil técnico
ativo da empresa. O baseline `0.68` não representa calibração corporativa. A
resposta pessoal expõe somente estado, finalidade, versão do aviso, retenção
configurada e canal de atendimento; vetor, score e referências privadas nunca
são retornados.

```powershell
$env:PHASE31_TEST_DATABASE_URL='postgresql://postgres:LOCAL_ONLY@127.0.0.1:55436/frequenia_phase25_test'
$env:FREQUENIA_DISPOSABLE_TEST_HOST='127.0.0.1'
python -m unittest discover -s tests -p "test_phase31_postgres_integration.py" -v
python tools/purge_biometrics.py --empresa-id UUID --limit 100
python tools/purge_biometrics.py --empresa-id UUID --limit 100 --execute
python tools/calibrate_biometrics.py C:\temp\dataset-sintetico.json --authorized --threshold 0.68
```

Purga é dry-run por padrão. O harness aceita somente dataset sintético ou
autorizado fora do Git, produz agregados e nunca promove limiar.
