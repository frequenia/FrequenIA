# Publicação web — acesso, cadastros e unidades

## Conteúdo e Git

Commit 0b056e6c2f4cfd555936f84018d26504697d30db, enviado e confirmado na
branch codex/recovery-operators-20261114. Trinta arquivos de aplicação:
login/recuperação com identidade FrequenIA; validação conjunta de nome pessoal,
telefone e CPF; mensagens por campo; busca de funcionário no cadastro facial;
retirada do logout duplicado; cadastro transacional de unidade/equipe e atalho
para configurar localização. Dependências e testes incluídos no mesmo commit.

Alterações antigas do Android, scripts de assinatura e otimização biométrica
preexistente preservadas fora deste commit. Não entram PNGs extras, prévias,
capturas, configurações privadas, APK, fotos ou embeddings.

## Preparação e banco

Imagem ARM64 sobre a publicação de 08100ed. Dockerfile com COPY explícito:
infra/aws/Dockerfile.web-release-20261122. Hashes de 30/30 arquivos extraídos
conferem com o checkout. Sintaxe: seis módulos Python, oito JavaScripts e
12 templates Jinja válidos. Unidades 9/9, validações pessoais/saída 7/7,
senhas 4/4, onboarding 6/6 e listagem 3/3; três suítes JavaScript passaram.
Unidades também tiveram 5/5 testes PostgreSQL sintéticos isolados, incluindo
unicidade e rollback de falhas de equipe e auditoria (documento específico).

Não há migration. Supabase xoof…esgx/main, modelo, limiar e política
biométrica preservados. Checagem remota preparada para devolver somente
indicadores de arquivos, SELECT 1, projeções WHERE FALSE, índices únicos,
permissões INSERT, vínculo do projeto e TLS verify-full. Nenhuma linha pessoal.

## Artefato imutável

Config: 08f2207048474feb8237f00df4e07f3ac021088289a30192790e364d9f6fe1c6.
Manifest ARM64: 5bf0707071be00c06740a9c70952b9a43525f7b6fd8345b55835d572c53093e0.
Pacote local: infra/aws/dist/frequenia-web-release-20261122.tar.gz.
Tamanho: 921.506.185 bytes; gzip -t integral válido.
SHA-256: 3d53e146a2785cd3ee68b0a318b9b6b2b7c0383efb1e43ffe9900351adad1f80.
Chave proposta:
runtime/frequenia-arm64-3d53e146a2785cd3ee68b0a318b9b6b2b7c0383efb1e43ffe9900351adad1f80.tar.gz.

## Estado e rollback

STS confirmou perfil restrito frequenia-publisher. Controlador consultado:
running, cost_lock=false, limite mensal 144.000 segundos; prazo anterior
23/11/2026 às 02h46min53s America/Sao_Paulo. Não reconfirmar este estado sem
nova consulta. Ponteiro anterior preservado, ETag
0e8185761825f225ad5455b0f7d3fb72; imagem anterior:
runtime/frequenia-arm64-cc6a81ae41a243caeab8e38f91370fa5cfbee4a04f6f3023cfc8425504a7d894.tar.gz.

Operadora confirmou upload, troca condicional e parada/início pelo controlador.
A credencial expirou antes de concluir o primeiro envio; ponteiro preservado.
Após confirmação específica, aws login foi aberto e concluído pessoalmente;
STS reconfirmou o principal restrito esperado. Autorizações de publicação
mantidas para o mesmo pacote e destino, sem alteração de escopo.

Envio concluído em 23/11/2026. Head-object confirmou 921.506.185 bytes, AES256
e metadado SHA-256 correspondente; não substitui hash de download integral.
Ponteiro trocado com If-Match do ETag anterior e relido com correspondência
exata. ETag resultante: 0711141cb9b44641a0d26a383f52f1f5.

Antes do boot, o controlador confirmou stopped e cost_lock=false. Início aceito;
última consulta running, sem trava, prazo automático em **23/11/2026 às
13h55min55s America/Sao_Paulo**. Acesso administrativo SSM encerrado; servidor
mantido na sessão controlada para teste pessoal autorizado da operadora.
Encerramento e confirmação stopped ao término da sessão permanecem pendentes.

## Verificação técnica no piloto

- Config efetivo igual a sha256:08f2207048474feb8237f00df4e07f3ac021088289a30192790e364d9f6fe1c6.
- Hashes internos 30/30 e assets públicos 12/12 correspondem ao pacote.
- HTTPS /health=200, /ready=200; quatro telas de acesso com layout novo e logo
  FrequenIA. Rotas /admin/unidades e /api/admin/unidades retornam 401 sem sessão.
- Serviço frequenia active; app, dispatcher, worker e Caddy ativos, ClamAV healthy.
- Banco: SELECT 1=1, project_match=1, tls=1, verify_full=1, projection=1,
  indexes=1, insert_permissions=1. Projeções de unidades/equipes/auditoria com
  WHERE FALSE e consultas somente de catálogo. Zero linhas pessoais retornadas.

Não houve migration, alteração de credencial de usuário, novo cadastro remoto,
renovação de política ou teste facial real pelo assistente. Teste funcional
pessoal permanece a cargo da operadora; os testes locais usaram fixtures.
Rollback operacional: ponteiro anterior e reinício controlado, sem downgrade.
