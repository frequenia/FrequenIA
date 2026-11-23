# Publicação de perfil, terminal, comprovante e permissões

Preparação local concluída em 23/11/2026; upload, ponteiro, migration e APK
dependem das etapas autorizadas. Não registrar preparação como publicação.

Imagem `frequenia:pilot-profile-20261123`, ARM64, baseada na imagem publicada
`frequenia:pilot-web-release-20261122`. Dockerfile explícito com 14 arquivos,
contexto isolado de aproximadamente 262 kB, sem diretórios privados, imagens
extras, testes, APK ou alterações biométricas preexistentes.

- Config: `35538b137d4f67e5c56c63b1bb81ab86d827c1ca2eb2b02d6e6a73a13782e803`.
- Manifest ARM64: `49aefa39c3a3f57fb2ccbb6b420a7cc1c3a82d081225438fd10b9dc80aa61a35`.
- Índice Docker: `bd3d7c78585d38f3db5523d52ae3d3f7802025de8118d6dd2d4976c6a01a85d1`.
- Arquivo: `infra/aws/dist/frequenia-profile-20261123.tar.gz`, 921.567.867 bytes.
- SHA-256 integral: `386e674528cff1937573a09e84e3a65c66db8764ed29108e863592fc427d89e6`.
- Verificação gzip integral aprovada. Execução local ARM64 indisponível por
  ausência de emulação; não foi tratada como teste runtime. Hashes e sintaxe
  devem ser verificados separadamente, antes da troca remota.

Banco preservado: `xoof…esgx/main`. Migration 027 cria somente a tabela privada
de avatares; SHA-256 `9433dc1129fa3b2c84701f0cfb9d42e8d5eee05c4c298857f4146267f5a7417c`.
Schema 001–026 → 027 ensaiado com dump criptografado sintético completo e
restore de public em novo PG/pgvector 17 sem rede. Cópia parada/preservada;
não comprova restore de backup real nem continuidade remota Supabase.
Evidência sintética é deliberadamente inelegível para aplicação remota.

Scripts privados para novo backup/restore e aplicação controlada preparados;
exigem alvo/TLS, hash, ensaio recente e confirmação específica. Nenhum segredo
é retornado. Migration aditiva permite rollback de imagem sem downgrade.

Rollback previsto: preservar ponteiro vigente e pacote SHA-256
`3d53e146a2785cd3ee68b0a318b9b6b2b7c0383efb1e43ffe9900351adad1f80`.
Antes da troca, reler ponteiro e ETag e usar atualização condicional.

Android: versão proposta 1.0.3+4, build release com assinatura privada da
operadora. Verificar assinatura e compatibilidade com certificado publicado
antes de substituir `apk/frequenia-latest.apk`. Não distribuir APK debug.

Verificações locais: 55 testes backend das três correções, 7 de foto de perfil,
18 Flutter e análise estática Android sem problemas. Capturas usam somente
fixtures sintéticas. Testes de publicação, backup real, foto no Supabase e
validação no aparelho ainda pendentes.
