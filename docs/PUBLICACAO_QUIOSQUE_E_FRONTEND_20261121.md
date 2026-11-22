# Quiosque responsivo e atualização da branch — 21/11/2026

## Escopo preparado

Pull fast-forward de `44270b6` para `10d1e61` na mesma branch
`codex/recovery-operators-20261114`, conforme solicitação da operadora.
Não foram mescladas branches divergentes. Preservadas as alterações locais
preexistentes. A proteção via textContent em ocorrências foi reaplicada sobre
o novo filtro/renderizador; conflito resolvido e sem entradas unmerged.
Backup Git dessa alteração mantido em stash `ee69c67c1234a9af0b9ad851da587c01560fbe0b`.

Incluídos os 18 arquivos do commit recebido e três arquivos do quiosque:
template, CSS responsivo e logo branca já rastreada. Não entram PNGs de marca
não rastreados, prévias, capturas, arquivos privados, APK ou dados pessoais.

O quiosque mantém a captura e a chamada facial existentes. A câmera ocupa a
altura disponível; painel acompanha sua altura, tipografia ampliada e logo
branca no gradiente do sistema. Prévia local usa câmera simulada, sem solicitar
permissão de mídia. Fluxo real só será exercitado privadamente pela operadora.

## Validação local

- Câmera UI 4/4; marcação de quiosque 7/7; ativação 8/8; ocorrências 17/17.
- Sintaxe de cinco JavaScripts válida; parse Jinja de dez templates válido.
- Nova projeção SQL de unidade/equipe executada em PostgreSQL sintético local,
  somente leitura e WHERE FALSE: colunas disponíveis, zero linhas retornadas.
  Container sintético parado após o teste.
- Conferidos SHA-256 dos 21 arquivos copiados na imagem contra o checkout.
- Layout normal validado sem rolagem em 1242x667, 1366x768, 1536x728,
  aproximadamente 1918x911, 1920x1080 e 1024x600. Botão e rodapé visíveis.
- Host x86 não executa a imagem ARM64. Validação do runtime depende da sessão AWS.

## Artefato e preservação

Dockerfile com COPY explícito: `infra/aws/Dockerfile.kiosk-responsive`.
Base atual: `frequenia:pilot-mobile-speed-20261116`, manifest
`b698dc931727a7183bcca03f2304f3da37f6a7ad5a057008d234b949eb6fb3fd`.
Nova configuração: `0ab3d332531c35675928cd3f8e95108171221c3fdf3fc722273d22f12bcef95e`.
Manifest da imagem ARM64:
`918098a8255ad067598a60eb4cc9b2078bdace5d03c88773a3d247f0df65b906`.

Imagem anterior preservada para rollback:
`runtime/frequenia-arm64-8ba116bd2f8ab0c70297550149751ce6d85a0953776336b50495cbb4bd4c34c2.tar.gz`.
Ponteiro consultado antes da preparação, ETag
`aa9bbb6334c0ded52c1907c2398b8bba`. Rollback operacional consiste em restaurar
esse ponteiro e reiniciar pelo controlador, sem downgrade de schema.

Banco, configuração privada, modelo facial, limiar, política e APK preservados.
Novos joins de unidade/equipe usam tabelas/colunas já presentes nas migrations
002–003. Não há migration nesta publicação.

## Estado

Publicação técnica concluída e abertura da câmera real com o novo layout
confirmada pela operadora. Encerramento da sessão controlada ainda pendente.
Não há homologação facial real pelo assistente.

Empacotamento local concluído, gzip -t válido. Pacote de 920.788.183 bytes,
SHA-256 `aee276b03548b8478091538eafa26b18531bccda93013784bde1ae5cb20673da`.
Chave publicada:
`runtime/frequenia-arm64-aee276b03548b8478091538eafa26b18531bccda93013784bde1ae5cb20673da.tar.gz`.

Operadora autorizou individualmente o envio do pacote validado, a atualização
condicional do ponteiro e a parada/inicialização da EC2 existente para teste.

Upload concluído e head-object confirmou 920.788.183 bytes, AES256 e metadado
SHA-256 correspondente. Esta conferência de metadados não substitui hash de
download integral. Ponteiro alterado com If-Match do ETag anterior; leitura de
volta confirmou a chave nova. ETag resultante `4cb5f6b586e28dd9b4c4de1e2c6d05cf`.

Reinicialização executada pelo controlador: parada confirmada antes de start.
EC2 running para uso pessoal da operadora, prazo automático em **21/11/2026,
19h29 America/Sao_Paulo**. Não foram alterados os limites mensais ou duração.

Validação externa após boot:

- ID efetivo do container confirmado igual à configuração nova
  `sha256:0ab3d332531c35675928cd3f8e95108171221c3fdf3fc722273d22f12bcef95e`.
- SHA-256 de 21/21 arquivos dentro do runtime corresponde ao checkout validado.
- HTTPS: 11/11 assets públicos correspondem aos hashes locais, incluindo o JS
  de captura preservado. Inicialmente houve DNS intermitente; nova resolução
  normal correspondeu à EC2 atual e /health=200, /ready=200 pelo domínio.
- /ready atual valida serviços de comprovantes, não o banco. Por isso foi
  executado teste separado no runtime: SELECT 1=1, TLS=1, verify-full=1 e
  correspondência exata do projeto via hash privado=1. URL e hostname do banco
  não foram exibidos ou registrados.
- Projeção nova de unidade/equipe validada no banco atual com WHERE FALSE:
  colunas disponíveis, zero linhas retornadas. Nenhuma linha pessoal lida.
- Sessão administrativa SSM encerrada; não houve acesso à câmera ou fotos pelo
  assistente. O teste no quiosque é realizado privadamente pela operadora.

Sem novo commit ou push nesta etapa. Pull recebido até `10d1e61`; alterações
locais preservadas, sem conflitos pendentes. Imagem anterior preservada no S3.

## Confirmação pessoal da operadora

A operadora informou que a câmera abriu no quiosque publicado com o novo
layout. Nenhuma foto, captura de câmera, embedding ou linha pessoal foi
solicitada ou recebida pelo assistente nesse teste. Esse resultado confirma
a abertura da câmera e a entrega visual; não comprova uma nova marcação,
acurácia ou latência do reconhecimento. A EC2 permanece na sessão controlada
para eventual continuação dos testes, com prazo automático às 19h29.
