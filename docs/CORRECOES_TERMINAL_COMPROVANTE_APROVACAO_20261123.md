# Terminal persistente, comprovante Android e aprovação de solicitações

Preparação local em 23/11/2026. Publicação remota e alteração de banco ainda
pendentes. Sem leitura de dados pessoais. Alterações anteriores preservadas.

## Terminal

A ativação já usava sessão permanente, mas compartilhava o cookie da sessão
de pessoas: login/logout e invalidação de sessão limpavam `terminal_ponto_id`.
Não há evidência de que fechar sozinho um navegador normal fosse suficiente
para apagar uma sessão válida. A correção separa a ativação em cookie assinado
`frequenia_terminal`, sem vencimento periódico da autorização, HttpOnly, SameSite Strict, Secure na
configuração de produção. Credencial de provisionamento não é persistida.
Login/logout não apagam esse cookie. O banco continua validando empresa,
status ativo e ausência de revogação em toda requisição autenticada do terminal.

Por preferência posterior da usuária, o prazo de 30 dias foi removido. O cookie
tem retenção de 365 dias no navegador, renovada a cada requisição validada;
uso regular dispensa reativação periódica. A assinatura não expira por idade,
mas o banco verifica a revogação em toda requisição. Após longa inatividade,
o navegador ainda pode eliminar o cookie pelo seu limite de retenção.

Ativações antigas válidas são migradas após validação no banco. Assinatura
inválida ou revogação negam acesso. Limpar cookies, usar janela
anônima ou trocar a chave de assinatura ainda exige nova ativação. Não há
promessa de persistência quando o navegador apaga seus dados.

## Comprovante Android

A usuária informou JPG rejeitada como tipo não permitido. `FilePicker` devolve
nome original separado do caminho temporário; `MultipartFile.fromPath` usava
o basename do cache. Quando o provedor devolve caminho sem extensão ou com
outro nome, o backend rejeita a extensão, apesar do MIME JPEG.

O cliente agora recebe `fileName` e envia o nome original tanto na criação
quanto na substituição do comprovante, incluindo a repetição após refresh.
Arquivos temporários ausentes produzem ApiException legível. Mantidos PDF,
JPEG e PNG até 10 MiB e todas as verificações de MIME, assinatura, armazenamento
privado e antivírus do servidor. Não houve flexibilização para arquivos falsos.
Teste reproduz o defeito com cache sem extensão e nome `comprovante.JPG`.
Validação no aparelho e novo APK permanecem pendentes.

## Aprovação

Por solicitação expressa da usuária, somente `administrador` da empresa
(Gestor de RH/Administrador) e `rh` aprovam/rejeitam. Ambos podem decidir nas
fases `pendente_gestor` e `encaminhada_rh`. Gestor conserva consulta no seu
escopo e encaminhamento ao RH, sem decisão. Endpoints retornam 403 e o domínio
também bloqueia a decisão por Gestor. `acoes_permitidas` controla os botões.
Solicitante continua podendo cancelar somente sua própria pendência.

O código persistido dos estados foi mantido, sem migration ou reescrita de
histórico. Texto de apresentação da pendência passa a “Pendente de análise”.
Tenant, escopo de gestão, locks, auditoria, notificações e estados finais
foram preservados. Fluxo separado de incidentes faciais não foi alterado.

## Validação local

- Python: 55 testes aprovados (terminal/ativação/ponto, workflow/HTTP/RBAC e
  comprovantes), somente fixtures sintéticas e conexões simuladas.
- Flutter: 18 testes aprovados, incluindo POST/PUT multipart após refresh,
  arquivo ausente, formulário de solicitação, fluxo facial e rótulos.
- Sintaxe JavaScript aprovada; sem teste remoto ou uso de foto real.

Para disponibilizar: publicar a versão do servidor e distribuir novo APK
release assinado, observando as confirmações do AGENTS.md. Nenhuma migration é
necessária para estas três correções. Migration 027 pertence ao recurso de
foto de perfil e tem salvaguardas próprias, ainda pendentes.
