# Prompt — Publicar as alterações existentes do FrequenIA na AWS

Publique no ambiente AWS de piloto que já existe as alterações implementadas e homologadas localmente nas Fases 30 e 31, mantendo a arquitetura e os recursos AWS já escolhidos para o FrequenIA.

O trabalho é de preparação e publicação do estado atual do repositório: jornada e marcação server-side, governança/ciclo biométrico, anexos e demais alterações existentes que façam parte da aplicação. Não iniciar uma nova fase funcional, não redesenhar a arquitetura e não substituir serviços existentes por outra plataforma.

## Limites

- Usar somente as stacks e a arquitetura que já existem em `infra/aws/`.
- Publicar para testar no ambiente de piloto; não acessar nem alterar produção.
- Usar exclusivamente banco/branch PostgreSQL de homologação e dados sintéticos.
- Não criar novas funcionalidades de produto. Alterar código de deploy/runtime apenas quando necessário para iniciar e operar corretamente o código já implementado.
- Não fazer commit, push, merge ou PR.
- Não excluir stacks, buckets, parâmetros, volumes, logs, filas ou banco nesta tarefa.

## Estado AWS existente

Preservar o piloto documentado em `infra/aws/README.md`:

- CloudFormation nas regiões `sa-east-1` e `us-east-1`;
- EC2 ARM64 já prevista, parada fora das sessões;
- imagem da aplicação privada em S3;
- HTTPS via Caddy e DuckDNS;
- SSM para administração e parâmetros de runtime;
- bucket privado de anexos, SQS/DLQ e ClamAV;
- DynamoDB e Lambdas já previstos para controlar sessões e custo;
- budget e watchdog já existentes.

Não criar ECS/EKS, novo VPC, ALB, NAT Gateway, RDS, ECR, domínio pago, CMK ou outra stack fora do plano atual. Se a arquitetura atual não comportar as alterações, registrar a limitação e pedir decisão antes de expandir.

## Antes de publicar

1. Leia `AGENTS.md`, `infra/aws/README.md`, os relatórios das Fases 30 e 31 e os arquivos de deploy/runtime.
2. Registre `git status --short`; preserve todas as mudanças preexistentes e não publique arquivos não relacionados por conveniência.
3. Identifique a versão exata do checkout/imagem que será publicada e faça inventário dos arquivos incluídos.
4. Rode a validação já definida para essa imagem e a suíte de contratos da infraestrutura; não declare validação que não foi executada.
5. Revise `.dockerignore`, `Dockerfile.arm64` e o conteúdo do arquivo compactado para excluir `.env`, `.secrets`, credenciais, chaves, dados pessoais, imagens, embeddings, dumps, caches, saídas e temporários.
6. Confirme que a versão contém migrations até `026` e que o banco alvo é um branch/projeto de homologação dedicado com TLS.
7. Gere uma cópia/backup recuperável do banco de teste e confirme a restauração antes de aplicar migrations.
8. Não ler nem imprimir o conteúdo de arquivos locais secretos. Validar presença/formato sem exibir valores.

## Autenticação e aprovação do deploy

- Verifique AWS CLI 2.32.0+ e a identidade com `aws sts get-caller-identity` sem expor credenciais.
- Use o perfil AWS já configurado. Se autenticação temporária for necessária, peça confirmação específica para executar `aws login` antes de iniciar essa autenticação.
- Antes de criar ou atualizar recursos, apresente conta/role, regiões, stacks, change sets, recursos alterados, estimativa/custo máximo configurado e rollback.
- A autorização para autenticar não autoriza automaticamente alteração de recursos; execute somente o escopo de publicação aprovado pelo usuário.
- Não use root, access keys permanentes ou permissões `AdministratorAccess` como atalho.

## Configuração do runtime

- Completar somente a integração dos componentes que já fazem parte do piloto e das Fases 28–31.
- Confirmar que S3 privado, SQS real e ClamAV ficam configurados pelo runtime existente.
- Se dispatcher e worker de anexos existentes precisarem de inicialização no EC2, adicioná-los ao mecanismo atual de contêineres/systemd, mantendo processos separados do Gunicorn, logs sanitizados, reinício controlado e encerramento correto.
- Não permitir provider de fila em memória fora de testes.
- Incluir as variáveis realmente necessárias da Fase 31, como `BIOMETRIC_AWAY_POLICY`; não adicionar novos valores legais por conta própria.
- Conservar os parâmetros SecureString já usados e a configuração do runtime no SSM sem revelar valores.
- Não mudar limites de instância, arquitetura, budget, regiões ou duração de sessão sem mostrar motivo e impacto e obter aprovação.
- Fazer health/readiness testar apenas dependências que a aplicação atual exige; não adicionar serviços novos.

## Banco e dados de teste

- Bloquear qualquer conexão a produção ou a banco cuja finalidade não esteja confirmada como homologação.
- Aplicar as migrations existentes `001`–`026` em ordem, sem criar ou renumerar migration.
- Se o banco já estiver em `025`, aplicar `026` após provar o restore do clone.
- Criar somente fixtures sintéticas necessárias para testar as alterações já existentes.
- Uma política/perfil biométrico de teste deve ser rotulada como fixture de homologação, sem declarar base legal ou retenção adequada para uso real.
- Não reutilizar fotos, embeddings, usuários ou marcações reais.

## Publicação mantendo a arquitetura

- Construir a imagem ARM64 com `infra/aws/scripts/build-arm64.ps1` e usar o artefato privado S3 previsto.
- Registrar checksum e digest da imagem; não reutilizar artefato remoto apenas por igualdade de tamanho.
- Publicar parâmetros de runtime de maneira protegida sem gravar valores sensíveis no terminal ou log.
- Preparar CloudFormation change sets para as stacks existentes e revisar cada recurso antes de executá-los.
- Publicar primeiro a versão de aplicação em sessão controlada; não deixar EC2 ligada ao final.
- Não publicar APK em loja. Se a distribuição do APK de teste fizer parte da solicitação, usar o bucket/prefixo já documentado e a chave de assinatura do piloto fora do Git.

## Teste externo

Usar navegador e dispositivos de teste com TLS válido, exclusivamente dados sintéticos ou voluntários formalmente autorizados.

Validar os fluxos que as alterações existentes afetam:

- login e autorização;
- jornada, próxima marcação e concorrência;
- escala/folga, quando fixtures sintéticas estiverem disponíveis;
- workflow Gestor → RH e visão efetiva;
- upload, varredura assíncrona e download de anexo;
- cadastro e verificação biométrica 1:1 com fixture autorizada;
- estado biométrico, bloqueio, desligamento, sessão e demais transições da Fase 31;
- separação de `falha_facial`;
- controles tenant/RBAC e respostas não enumeráveis.

Não declarar resultados de capacidade/precisão como SLO de produção. Não realizar testes de carga que possam gerar custo ou indisponibilidade sem apresentar plano e obter aprovação.

## Rollback e encerramento

- Manter artefato anterior privado e identificado para rollback.
- Se migrations, readiness, autenticação, isolamento ou fluxo principal falharem, reverter a versão da aplicação e restaurar o banco de homologação quando necessário.
- Não reverter/destruir uma migration automaticamente se isso ameaçar integridade dos dados.
- Após o teste, encerrar a sessão pelo controlador existente e conferir que a EC2 está parada.
- Manter stacks/recursos existentes; não executar limpeza destrutiva.
- Informar custos residuais potenciais de EBS, S3, DynamoDB, SQS, SNS, logs e budget.

## Relatório final

Registrar em `docs/PUBLICACAO_AWS_ALTERACOES_EXISTENTES.md`:

- identidade AWS mascarada e regiões;
- commit/ref local ou fingerprint do checkout e digest da imagem;
- stacks/change sets executados e recursos alterados;
- confirmação de banco de homologação e migrations aplicadas;
- URLs de teste e fluxos verificados;
- logs/métricas sanitizados, falhas e rollback;
- resultado das suítes executadas;
- estado final da EC2 e recursos mantidos;
- custos/recursos residuais;
- limitações do piloto.

Concluir somente depois de comprovar que o código atual está acessível no piloto, que os fluxos existentes funcionam, que a instância foi parada e que nenhum dado/serviço de produção foi acessado.
