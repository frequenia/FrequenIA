# Diagnóstico de criação de ocorrência — 16/11/2026

A operadora informou falha no Android com e sem comprovante. A resposta
genérica corresponde ao tratamento de erro 500 de `create_occurrence`; a causa
no ambiente ativo ainda não foi identificada.

Preparação local:

- Criação de correção de tipo passou em PostgreSQL 17 isolado, sem rede ou
  portas publicadas, com as 26 migrations e fixtures sintéticas: 1/1 teste.
- Workflow de ocorrências: 17/17 testes; comprovantes: 7/7 testes.
- Adicionado diagnóstico de erro que registra somente etapa fixa e SQLSTATE
  validado. Não registra exceção, traceback, SQL, parâmetros ou identidade.
- Operador somente leitura de catálogos verifica tabelas, colunas, workflow,
  permissões e bypass de RLS. Validado no banco sintético: seis indicadores 1.
  O indicador de RLS descreve capacidade do papel da conexão, não conclusão
  sobre as políticas efetivas da conexão do runtime.
- Container sintético parado e preservado. Banco restaurado com dados reais
  não foi acessado por esse ensaio.

Pendente: execução privada do diagnóstico de catálogo no banco atual pela
operadora. Nenhuma migration, alteração de dados, publicação ou mudança de
ponteiro foi executada nesta investigação. O diagnóstico de logging ainda é
somente local e não altera o servidor publicado.

## Resultado privado informado pela operadora

`tabelas=1; colunas=1; workflow=0; permissao_insert=1;
permissao_select=1; rls_bypass=1`.

O indicador workflow procura a restrição nomeada da migration 018 que contém
`pendente_gestor`. Seu valor zero, isoladamente, não diferencia restrição antiga
de restrição ausente ou renomeada. Ampliado o diagnóstico somente de catálogo
para identificar restrição legada, default, constraint de decisão e índice.

Reprodução adicional: uma restrição com os estados legados da migration 008
rejeita a criação atual com SQLSTATE 23514 na etapa correction; removendo apenas
essa restrição adicional do ensaio, a criação volta a passar. Testes PostgreSQL
isolados: 2/2. Nenhuma alteração do banco ativo realizada.

Possível correção, condicionada ao diagnóstico: aplicar a migration 018
existente, SHA-256
`4df3f2b03b2f2a81283e37b91e8cbe0a3d600de6652e5196800c07e4c4aaddbe`.
Ela adapta estados de solicitações, regra de decisão e índice. Não reescreve
marcações ou snapshots de jornada. Requer backup atual validado em isolamento,
preflight que descarte aplicação parcial e confirmação específica. Transação
falha com rollback; após commit não haverá downgrade automático. Preservar
backup e interromper o fluxo em caso de divergência. Não exige novo APK ou
reconstrução da imagem para a compatibilidade de estado, se confirmada a causa.

A consulta adicional de catálogo falhou por resolução DNS antes da execução SQL.
Classificação automatizada do log privado retornou somente `dns`; nenhum conteúdo
bruto foi exibido. Operador ajustado para até três tentativas de consulta em
falhas transitórias de rede, com connect_timeout de oito segundos e
statement_timeout de quinze segundos. Nova execução privada pendente.

## Confirmação do workflow e preparo da correção

Operadora informou `restricao_legada=1; padrao_atual=0; decisao_atual=0;
indice_atual=0`. O schema continua com a regra legada da migration 008 e sem
os quatro elementos esperados da 018. Isso corresponde à reprodução local de
rejeição de `pendente_gestor` (23514). A criação deve ser retestada após a correção;
outros erros ainda podem existir.

Preparados operadores separados para ensaio e aplicação. O ensaio exige backup
criptografado novo, com hash e idade de até duas horas; cria PostgreSQL local
sem rede nem portas, recompõe 001–026 sem 018, restaura somente public e ensaia
a 018. O destino é parado e preservado, junto com evidência sem dados pessoais.
Isso não comprova continuidade dos schemas internos Supabase.

Ensaio integral do operador executado com backup exclusivamente sintético,
contendo uma solicitação legada: restore=1, migration=1, contagens preservadas=1,
estados compatíveis=1. Artefato sintético explicitamente inelegível para o
operador remoto. Nenhum backup real foi usado nesse teste.

Aplicação remota preparada, ainda NÃO executada: exige evidência recente do
ensaio, hashes válidos, alvo mascarado e CA verificados, preflight exato dos
quatro elementos legados e confirmação `APLICAR-WORKFLOW-018`. A migration
existente executa em transação, com lock_timeout de 5s e statement_timeout de
60s por instrução. Em falha antes do commit, rollback da transação. Após commit,
sem downgrade automático; falha da pós-validação interrompe os testes.

Pendente autorização específica para cópia local com backup atual real e,
depois do ensaio, confirmação separada para aplicar a 018 no banco ativo.

Backup e ensaio local com dados atuais autorizados pela operadora. Tentativa de
backup interrompida no teste de conexão por DNS, antes de iniciar dump.
Verificação posterior sanitizada: DNS do endpoint no Windows, WSL e Docker OK;
DNS público no Windows e Docker OK. Nenhum endereço foi exibido. Acrescentadas
ao operador de backup até três tentativas para falhas transitórias de conexão
e PGCONNECT_TIMEOUT=8; não há retry de dump nem sobrescrita de arquivo parcial.
Verificação de identidade TLS preservada. Backup novo ainda pendente.

Backup novo concluído pela operadora em 16/11/2026, arquivo
`supabase-pilot-20261116-215449.dump.gpg`, 548.047 bytes, SHA-256
`67311c81e5fffac141ea7e737ba3033bf520d78de8a5df099d5878dc46ef3249`.
Hash recalculado e confirmado independentemente, sem abrir o conteúdo cifrado.
Operador de ensaio aberto para entrada privada da frase secreta. Aplicação no
banco remoto continua pendente de ensaio bem-sucedido e confirmação separada.

Ensaio do backup atual concluído pela operadora: backup_restaurado=1,
migration_aplicada_na_copia=1, contagens_preservadas=1, estados_compativeis=1.
Evidência `workflow-018-rehearsal-20261117005618.evidence.txt` conferida pelo
assistente contra os hashes esperados e idade de até duas horas. Container local
confirmado parado, NetworkMode=none e sem port bindings. Backup e cópia
preservados. Confirmação específica para a aplicação remota solicitada; ainda
nenhuma migration executada no Supabase ativo.

Operadora aprovou especificamente a aplicação da migration 018 no banco atual.
Operador privado aberto com a evidência validada; aguardando execução pessoal
da autenticação e confirmação literal. Resultado remoto ainda não recebido.

Resultado remoto informado pela operadora: `migration_aplicada=1;
restricao_atual=1; padrao_atual=1; decisao_atual=1; indice_atual=1`.
O operador só emite essa linha após commit e pós-validação de catálogo.
Backup e destino local mantidos. Correção de compatibilidade aplicada;
teste funcional de criação no Android ainda pendente. Não foi necessário
publicar APK ou imagem, alterar ponteiro, iniciar EC2 ou executar downgrade.

Verificação técnica posterior: EC2 existente consultada e confirmada running.
Primeiro acesso pelo domínio falhou por DNS; acesso ao IP corrente com resolução
fixada por requisição e validação HTTPS do hostname retornou /health=200 e
/ready=200. Resolução nativa do domínio voltou a funcionar em seguida. Nenhuma
configuração DNS, TLS ou recurso remoto foi alterado. Solicitado à operadora
teste funcional pessoal no Android, sem que o assistente acesse ou envie linhas
pessoais. Sessão controlada existente permanece para esse teste.

## Resultado funcional

Operadora confirmou no Android que a solicitação apareceu no histórico como
pendente de análise. Falha de criação relatada resolvida após alinhamento do
workflow do banco com a API publicada. Sem novo APK/imagem e sem alteração de
marcações ou jornadas por esta correção. Aprovação da solicitação e eventuais
efeitos na jornada não fazem parte dessa evidência. Teste com comprovante não
foi confirmado separadamente. Encerramento da sessão controlada iniciado.

Encerramento executado pelo controlador existente (`pilot-session.ps1 -Action
stop`). Resposta inicial aceitou a ação; aguardada a transição e realizada nova
consulta EC2, confirmando `stopped`. Backup criptografado e cópia local de ensaio
preservados. A execução não exigiu nova publicação de código.
