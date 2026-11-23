# Meu perfil e avatar privado — preparação local

Implementado em 23/11/2026. Publicação remota e migration ainda pendentes.

Tela responsiva com identidade, cartões de dados pessoais/profissionais,
jornada e estado biométrico preservados. Ficha única com divisórias; avatar
clicável com câmera e ícone de pessoa quando não há foto. Prévia e confirmação
para salvar ou remover foto; mensagens de erro e tema compartilhado.

A pedido da usuária, a foto será armazenada no PostgreSQL do Supabase atual,
em `fotos_perfil` (migration 027). Não usa pasta pública, serviço externo ou
outro projeto. Uma linha por usuário; substituição elimina a versão anterior
do banco ativo. Remoção exclui a linha, sem prometer eliminação de backups.
Avatar não alimenta cadastro facial, embeddings ou treinamento.

Entrada JPG/PNG/WebP até 5 MiB e 16 milhões de pixels, mínimo 64 por eixo,
sem animação. Pillow decodifica e reprocessa em JPEG quadrado 512×512, sem EXIF,
máximo 256 KiB. Nome do arquivo não é armazenado. Nunca persiste o original.
Estimativa máxima: 1.000 avatares ocupam 250 MiB de conteúdo, além de índices,
WAL e backups; considerar a capacidade disponível do plano Free antes de publicar.

`GET/PUT/DELETE /api/perfil/foto` exige sessão autenticada de administrador da
empresa, RH, gestor ou funcionário. Não recebe usuário/empresa de cliente;
usa somente `g.auth_context.user_id`. Mutações exigem token CSRF da página;
respostas `private, no-store` e `nosniff`. GET sem avatar retorna 204; falha
de estrutura/conexão retorna 503 sem esconder a indisponibilidade como ausência.
RLS sem políticas e privilégios revogados de public/anon/authenticated impedem
acesso direto pela API pública Supabase. Backend precisa ser proprietário ou
ter privilégio explícito e BYPASSRLS; verificar a role antes da publicação,
sem conceder acesso ao cliente. Nenhuma chave Supabase é enviada ao navegador.

Validação local:

- 7 testes unitários de imagem, metadados, autenticação, CSRF, vínculo à própria
  conta, limite, substituição/remoção, falhas e fechamento da conexão.
- Ensaio da migration em novo banco sintético no PostgreSQL local sem rede:
  upsert, limite de bytes, privilégios, RLS e cascade aprovados. Container parado
  após o teste; nenhum backup ou banco anterior foi excluído.
- Regressões de cadastros e unidades: 16 testes aprovados.
- Prévia real do template, APIs simuladas, dados e imagem sintéticos: seleção,
  confirmação, upload, recarregamento e remoção; computador 1280×800 e celular
  390×844, sem transbordamento horizontal.

Prévia: `http://127.0.0.1:5185/perfil-preview`. É uma demonstração local,
com armazenamento em memória; não comprova persistência no Supabase.

Para publicar: backup novo e restore isolado validados, confirmação específica
para migration 027 no alvo mascarado `xoof…esgx/main`, verificar permissões da
role de runtime e aplicar somente essa migration. Em seguida publicar imagem
com os novos arquivos pelas confirmações do AGENTS.md. Deploy antigo ignora a
tabela nova, permitindo rollback da imagem sem downgrade do schema.
Teste autenticado remoto permanece pendente e deve usar fixture sintética.
