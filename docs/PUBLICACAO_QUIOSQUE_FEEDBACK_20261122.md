# Quiosque: câmera, confirmação e alertas — 22/11/2026

## Preparação local

Alteração solicitada pela operadora: preencher o espaço da câmera, mostrar
nome, horário oficial e tipo após marcação confirmada, e explicar falhas em
alertas com orientação. A visualização usa object-fit: cover; o quadro enviado
ao reconhecimento continua com as dimensões originais do vídeo.

O nome é retornado apenas após marcação confirmada, na consulta restrita à
empresa do terminal. Falhas biométricas continuam sem revelar a existência da
matrícula. A resposta de sucesso tem Cache-Control: no-store. O diálogo usa
textContent, limpa os dados ao fechar/sair e fecha a confirmação em dez
segundos. Erros permanecem até a ação da pessoa. Falhas de rede orientam
consultar o histórico antes de repetir uma marcação de resultado incerto.

Validações: 21/21 testes Python do quiosque; suíte JavaScript de confirmação,
horário oficial, alerta, limpeza e texto seguro; diff sem erros de whitespace.
Prévia no navegador com vídeo e respostas sintéticos. Desktop 1366x768 sem
rolagem; vídeo em cover com largura igual ao contêiner. Alerta em 390x844
inteiramente acessível. Nenhuma câmera ou linha pessoal real usada.

Dockerfile com quatro COPY explícitos: infra/aws/Dockerfile.kiosk-feedback.
Base local da publicação anterior:
`cffa6efa8c2cad1275e86c50eac8aa8a6adb78a16d5b46e0ea9451306d1dc643`.
Build confirmou essa base e produziu manifest ARM64
`6fde987959c4ca44cc63bac4197dc4b33afeedbbbe36b1ffa65c39c55c95749a`,
config `fa548651d06943f323126412da99f8527513533f99abed6e8426f4dba3fcd905`.
Conferidos SHA-256 de 4/4 arquivos extraídos sem executar a imagem.

Pacote concluído: infra/aws/dist/frequenia-kiosk-feedback-20261122.tar.gz,
920.880.294 bytes; gzip -t integral válido. SHA-256:
`2c4ee03119d1be3611c76bc8844179ca2ead9e761055076fa7246212a8dbd5f9`.
Chave imutável proposta:
`runtime/frequenia-arm64-2c4ee03119d1be3611c76bc8844179ca2ead9e761055076fa7246212a8dbd5f9.tar.gz`.

Não entram outras alterações locais, PNGs não rastreados, prévias, testes,
segredos, APK ou dados. Banco, schema, modelo, limiar e política preservados.
Não houve novo commit, push ou pull nesta etapa.

## Banco e TLS

Não há migration. A nova projeção usa usuarios.nome e funcionarios.usuario_id,
campos existentes. Verificação remota de vínculo/TLS somente após autenticação
e início autorizado; não consultar linhas pessoais.

## Publicação e rollback

Login renovado pessoalmente pela operadora; STS confirmou o principal restrito
frequenia-publisher na conta esperada. Controlador confirmou EC2 stopped,
cost_lock=false e uso mensal 63.071/144.000 segundos antes da publicação.
Ponteiro anterior confirmado como pacote aee276b0…20673da, ETag
`4cb5f6b586e28dd9b4c4de1e2c6d05cf`, preservado em arquivo local de rollback.

A operadora confirmou separadamente envio do pacote, troca condicional do
ponteiro e início pelo controlador com limite de quatro horas. Upload concluído;
head-object confirmou 920.880.294 bytes, AES256 e metadado SHA-256 igual ao
pacote local. Esta conferência não substitui hash de download integral.

Ponteiro trocado com If-Match do ETag anterior; nova leitura correspondeu à
chave proposta. ETag resultante: `95d691159fdb80afea403337f02364e7`.
Start autorizado aceito pelo controlador. Prazo automático da sessão:
**22/11/2026 às 22h13min30s America/Sao_Paulo**. Última consulta: running,
cost_lock=false. Acesso administrativo SSM encerrado; servidor mantido ligado
para teste pessoal conforme pedido da operadora. Encerramento da sessão e
confirmação stopped ainda pendentes; não declarar que já foi desligado.

## Verificação técnica no piloto

- Container efetivo com config ARM64
  `sha256:fa548651d06943f323126412da99f8527513533f99abed6e8426f4dba3fcd905`.
- Hashes de 4/4 arquivos dentro do runtime correspondem ao checkout validado.
- Serviço frequenia ativo; app, dispatcher, worker e Caddy ativos, ClamAV healthy.
- HTTPS /health=200 e /ready=200; CSS e JavaScript públicos com hashes locais.
- Verificação adicional de banco no runtime: SELECT 1=1, TLS=1,
  verify-full=1 e correspondência por hash do projeto esperado=1.
- Projeção nova validada com WHERE FALSE: colunas id/nome disponíveis,
  zero linhas pessoais retornadas. Nenhuma migration ou gravação executada.
- Nenhum teste facial real foi feito pelo assistente. Teste pessoal e
  confirmação da experiência com o novo diálogo permanecem pendentes.

Rollback previsto: restaurar condicionalmente o ponteiro anterior e reiniciar
pelo controlador, preservando ambas as imagens e sem downgrade de schema.
Antes do envio, obter aprovações específicas de upload, ponteiro e sessão após
mostrar hash, tamanho, alvo, efeito e custo/tempo. Ao final da sessão, encerrar
pelo controlador e confirmar stopped.

## Limites da validação

Os testes locais não comprovam nova marcação no piloto nem acurácia ou latência
facial real. A publicação não renova política, consentimentos ou perfil e não
altera a vigência biométrica existente. Teste pessoal autorizado deve ocorrer
privadamente, sem compartilhar fotos, embeddings ou respostas pessoais.
