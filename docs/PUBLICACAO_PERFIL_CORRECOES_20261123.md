# Publicação de perfil, terminal, comprovante e permissões

Preparação local em 23/11/2026. Migration e APK concluídos nas etapas abaixo;
ativação da imagem corrigida no servidor ainda em andamento.

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
  ausência de emulação; não foi tratada como teste runtime. Os 14 arquivos
  foram extraídos do pacote/imagem e seus hashes conferem com o manifesto;
  sintaxe dos oito Python e três templates aprovada, sem importar app/secrets.

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

Commit de implementação `9670c0d240a049cc9aeecc64f48b8e9e6402dc83`, push
confirmado em `codex/recovery-operators-20261114`. Nenhum arquivo privado,
artefato binário ou alteração biométrica preexistente entrou no commit.

## Backup real e APK — atualização de preparação

Operadora concluiu backup lógico criptografado em 23/11/2026, 11h12min17s
America/Sao_Paulo: 561.600 bytes, SHA-256
`21eca0cfb4f4c15e2a68019ef296333d825e5d75ba648aa4ae48ae0ebb6ecf27`.
Arquivo privado `supabase-pilot-20261123-111217.dump.gpg`, preservado.
Resultado informado: restore=1, migration_na_copia=1, contagens_preservadas=1,
avatar_privado=1. Evidência `profile-027-rehearsal-20261123142307.evidence.txt`.
Após confirmação específica, operadora aplicou a migration 027 e informou:
`migration_aplicada=1; tabela=1; rls=1; privada=1; permissao_backend=1`.
Backup e cópia de ensaio preservados; teste funcional permanece pendente.

APK 1.0.3+4 gerado: 54.415.866 bytes, SHA-256
`112331d3d7a67dca9857a1d4483b8cace55b6fea1090b30c9e75ab437175e60e`.
Assinatura release APK v2 válida, RSA 4096. Certificado
`35e5307574f95d0bc2382eed60c842a5f6bd74c291153d5419da6f1e25f12197`.
Download integral do latest confirmou versão 1.0.2+3/hash anterior e certificado
`dee304b21e4e2b2481a2210eaecc8088111f4e550e623a7edb8cc61a4d8279dd`.
Certificados divergem; operadora escolheu explicitamente publicar exigindo
desinstalação/reinstalação e autorizou objeto versionado e latest. Envio
concluído em `apk/frequenia-1.0.3-pilot.4.apk` e `apk/frequenia-latest.apk`.
Download público integral do latest recalculou SHA-256 igual ao novo APK.
Versão 1.0.2 preservada. Não houve acesso à chave ou sua senha pelo assistente.

## Correção do empacotamento e ativação

Primeira troca de ponteiro autorizada/concluída, ETag
`9b68f55d122042e68b84e109c8112317`. Runtime manteve containers anteriores;
diagnóstico sanitizado revelou `max depth exceeded` na carga Docker. A base
tem 118 camadas e 14 COPY separados produziram 132, acima do limite de 128
do Docker da EC2. Também faltava a tag `frequenia:pilot` esperada pelo boot.
Pacote intermediário com duas tags, hash `2f1716f8…36f4b90`, não foi enviado
porque mantinha 132 camadas. Nenhuma conclusão de publicação foi inferida do
simples retorno de /health da versão anterior.

Dockerfile corrigido usa um COPY de payload isolado. Preparador lista somente
os 14 arquivos revisados. Empacotador inclui ambas as tags e rejeita imagens
acima de 125 camadas antes de alterar tag ou gravar pacote; regressão com a
imagem de 132 camadas foi rejeitada como esperado.

Pacote final autorizado: `frequenia-profile-20261123-single-layer.tar.gz`,
921.559.832 bytes; SHA-256
`ae2c7b7d52215d882ec48ff6a26d5aa89648970a927840d625abdf5cd361bd65`.
Config `69862cb56cadd4539e630a3222092a47f6274e5fee7a246307621f3d8c6f8e98`;
manifest ARM64 `5b66e43bed095e43547aaee46f339ed390d00385bf9468b1f743c44525924393`.
Archive valida gzip, duas tags e 119 camadas; 14/14 arquivos extraídos
conferem com o manifesto e sintaxe Python/templates passou. Sem alteração de
código de aplicação entre candidatos, apenas a organização de camadas/tags.

Conexão interrompeu dois envios grandes; upload retomável em partes de 32 MiB
preserva ETags locais, valida hash antes de iniciar e usa retries adaptativos.
Não trocar o ponteiro final antes de confirmar conclusão e metadados S3.
Operadora autorizou envio final, troca condicional e recarga do serviço.
Posteriormente pediu explicitamente deixar o sistema ligado após atualizar;
manter sessão controlada vigente e informar seu prazo, fechando a sessão SSM.
