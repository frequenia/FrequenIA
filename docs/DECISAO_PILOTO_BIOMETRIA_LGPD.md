# Decisão do controlador — piloto biométrico 1:1 (minuta)

Data da minuta: 24/10/2026. **Não é aprovação jurídica nem autorização de
ativação.** Preencher e aprovar pelo controlador/responsável antes do uso com
pessoas reais. Não anexar fotos, embeddings, URLs, credenciais ou termos de
titulares a este arquivo.

## Decisões já declaradas pela controladora

- Hipótese escolhida para este piloto: consentimento específico e destacado
  dos titulares adultos voluntários, para a finalidade determinada de cadastro
  e verificação facial 1:1, conforme art. 11, I, da LGPD. A controladora
  declarou que a participação dos desenvolvedores é voluntária. Essa escolha
  ainda depende da identificação formal de quem exerce o papel de controlador
  e não abrange treinamento de IA.
- Finalidade desta liberação: cadastro e verificação facial **1:1** no piloto
  FrequenIA. Treinamento de IA não integra o piloto; eventual treinamento
  exige decisão, aviso e implementação separados.
- Participantes: adultos voluntários, incluindo desenvolvedores e testadores
  externos; participação recusável sem prejuízo. Funcionários reais de
  empresas não foram incluídos nesta liberação.
- Alternativa em caso de recusa, impossibilidade ou falha: conferência humana
  e registro de ponto sem punição automática.
- Revisão do piloto após 60 dias; a revisão não é prazo de eliminação nem
  autoriza retenção indefinida.
- O prazo de 365 dias inicialmente proposto para embeddings foi substituído
  pela decisão v1.1 ao fim deste documento. O prazo das fotos antigas
  vinculadas no Cloudinary não foi ampliado.
- Canal informado: `frequenia@gmail.com`.
- A controladora declarou que existem termos/e-mails individuais de aceite
  guardados privadamente. Não se verificaram versões, cobertura ou conteúdo;
  esses documentos não devem ser enviados ao assistente.

## Registro ainda necessário antes da ativação

1. **Identificação do controlador:** a hipótese do art. 11, I, foi escolhida
   para o piloto voluntário, mas “os desenvolvedores” não identifica por si só
   a pessoa natural ou jurídica que toma as decisões do tratamento. Registrar
   o nome da pessoa/empresa controladora, contato e referência da decisão. Se
   houver controladoria conjunta, identificar cada controlador e suas
   responsabilidades. A declaração geral “aprovo a LGPD” não substitui essa
   identificação.
2. **Necessidade e proporcionalidade:** explicar por que o teste com biometria
   real é necessário, seu alcance mínimo, quem acessa e por que a alternativa
   humana é suficiente quando alguém recusa ou falha.
3. **Aviso e aceites:** aprovar texto e versão do aviso, o momento anterior ao
   cadastro, o canal de atendimento e a forma de conferir privadamente que
   cada participante recebeu esse aviso e aceitou especificamente o 1:1.
   Guardar apenas referência interna não sensível no registro do piloto.
4. **Retenção e direitos:** aprovar os prazos por categoria, data inicial,
   bloqueio no vencimento, hold excepcional, revogação, eliminação no Supabase
   e no Cloudinary e prevenção de reativação após restore. A revisão de 60
   dias não substitui essas regras.
5. **Incidentes:** designar responsável, canal interno, fluxo de contenção,
   avaliação de risco, comunicação e registro de decisão.
6. **RIPD:** registrar a avaliação de risco e a decisão fundamentada sobre
   elaborar ou não um Relatório de Impacto, com responsável e referência.
7. **Acurácia e equidade:** aprovar protocolo de calibração com dados
   formalmente autorizados, métricas e critérios de parada. O limiar `0.68`
   não muda automaticamente.
8. **Decisão final:** responsável, data, versão desta decisão, condições e
   aprovação explícita para ativar somente após validação técnica no piloto.

## Pendências técnicas independentes da assinatura

- **Concluído em 25/10/2026:** imagem do hotfix publicada e validada no runtime
  ARM64 com o ID esperado; serviço e containers permaneceram ativos, sem
  reinícios, e HTTPS, `/health` e `/ready` responderam 200.
- **Concluído em 25/10/2026:** vínculo mascarado com `xoof…esgx/main`,
  `sslmode=verify-full`, CA legível e TLS cliente ativo foram confirmados por
  indicadores booleanos, sem mostrar URL, host, segredo ou linha pessoal.
- Confirmar que a política biométrica e o perfil técnico correspondem à
  decisão aprovada e que o bloqueio/eliminação dos prazos funciona. Não
  consultar pessoas reais pelo assistente.
- Executar testes autenticados com contas e fixtures sintéticas. Uso 1:1 por
  participantes reais requer confirmação específica posterior.

Nenhuma biometria deve ser ativada por esta minuta sozinha.

## Pacote de decisão v1.0 — aprovado pela controladora

Este pacote consolida as escolhas declaradas até 25/10/2026. A responsável pela
`Equipe FrequenIA` aprovou expressamente o conjunto em 25/10/2026. A aprovação
formaliza a decisão do piloto, mas não equivale ao aceite individual dos
titulares e não autoriza automaticamente cada operação remota; política,
perfil, testes e ativação continuam sujeitos às confirmações operacionais
específicas previstas no plano de publicação.

1. **Controlador:** `Equipe FrequenIA`, denominação operacional informada pela
   responsável pelo projeto. Canal dos titulares e de revogação:
   `frequenia@gmail.com`. Para uso fora deste piloto interno, a denominação
   deverá ser complementada pela identificação jurídica ou da pessoa natural
   responsável.
2. **Titulares e hipótese:** somente desenvolvedores adultos que participem
   voluntariamente. Hipótese escolhida: consentimento específico e destacado
   para dado biométrico sensível, art. 11, I, da LGPD. Recusa e revogação não
   causam prejuízo. Cada aceite deve referenciar o aviso v1.0 e permanecer
   guardado privadamente.
3. **Finalidade e proporcionalidade:** validar, em escala mínima, cadastro e
   verificação facial 1:1 para registro de ponto no piloto. Não há busca global,
   identificação de desconhecidos, compartilhamento com outro controlador ou
   treinamento de IA. A finalidade não será ampliada sem nova decisão e novo
   aceite.
4. **Alternativa humana:** em recusa, falha, indisponibilidade, acessibilidade ou
   revogação, a pessoa usa conferência humana e registro alternativo, sem punição
   ou decisão automática desfavorável. Contestação pelo canal informado.
5. **Aviso:** o `Aviso Piloto Biométrico FrequenIA v1.0` deve ser entregue antes
   do cadastro, junto ao termo/e-mail individual. Deve informar controlador,
   finalidade 1:1, categorias tratadas, armazenamento, ausência de treinamento,
   prazos, alternativa, revogação, eliminação, canal e direitos.
6. **Retenção:** embedding por no máximo 365 dias desde o cadastro; referências
   e fotos anteriores no Cloudinary por no máximo 365 dias desde 25/10/2026.
   Revisão operacional em 60 dias, sem renovação automática do prazo. No
   vencimento ou revogação, bloquear imediatamente o uso; eliminar de forma
   auditável após verificar hold excepcional documentado. Restore não pode
   reativar material eliminado. Exclusão no Cloudinary permanece uma execução
   operacional separada e deve ser comprovada sem abrir as imagens.
7. **Incidentes:** responsável operacional `Equipe FrequenIA`, canal
   `frequenia@gmail.com`. Diante de suspeita, bloquear o fluxo afetado,
   preservar evidências sem conteúdo biométrico, restringir acesso, avaliar
   risco/dano, documentar a decisão e realizar as comunicações legalmente
   aplicáveis. Nenhum segredo, foto ou embedding entra em ticket ou e-mail.
8. **RIPD e decisão de prosseguir:** adotar como RIPD simplificado inicial o
   inventário, as ameaças, salvaguardas e riscos residuais da Fase 33, com esta
   decisão como complemento. Prosseguir apenas com os desenvolvedores
   voluntários; elaborar revisão formal antes de incluir testadores externos,
   funcionários de clientes, treinamento ou escala de produção.
9. **Acurácia e equidade:** manter o limiar `0.68`, sem promoção automática.
   O piloto é funcional e não gera alegação de precisão ou equidade. Toda
   decisão negativa admite alternativa humana. Registrar somente resultados
   agregados e interromper o uso diante de falsa aceitação observada, falhas
   repetidas ou impacto desigual que exija investigação. Dados reais não serão
   reutilizados para calibrar ou treinar sem decisão separada.
10. **Condições de ativação:** imagem, vínculo e TLS já validados; antes do uso
    real, criar no banco a política v1.0 e o perfil técnico v1.0, testar
    readiness com conta/fixture sintética, confirmar individualmente o aceite
    de cada desenvolvedor e obter confirmação específica para ativar e testar o
    fluxo real. Encerrar toda sessão AWS pelo controlador de custos.

Referências internas propostas para os registros imutáveis:

- base legal: `LGPD-art11-I-consentimento-especifico-piloto-dev-v1`;
- aviso: `Aviso-Piloto-Biometrico-FrequenIA-v1.0`;
- decisão/RIPD: `DECISAO-PILOTO-BIOMETRIA-LGPD-v1.0-2026-10-25`;
- relatório técnico: `FASE-33-v1.0-2026-10-25`.

**Decisão final:** aprovada pela `Equipe FrequenIA` em 25/10/2026, versão 1.0,
somente nas condições e no escopo acima. Qualquer inclusão de outras pessoas,
treinamento, nova finalidade, novo prazo ou mudança material exige nova versão.

## Emenda de decisão v1.1 — retenção e vigência

Em 25/10/2026, a `Equipe FrequenIA`, na qualidade operacional de controladora,
aprovou substituir apenas as regras de vigência e retenção da versão 1.0:

- a primeira política e o perfil técnico vigoram de 25/10/2026 a 24/11/2026;
- embeddings podem ser mantidos por no máximo 1.825 dias desde cada cadastro;
- a justificativa operacional é permitir avaliação longitudinal do piloto e
  reduzir recadastros, limitada aos desenvolvedores adultos voluntários;
- a necessidade e proporcionalidade serão revistas em 30 dias. A continuidade
  exige uma nova versão, sem sobreposição, antes do vencimento;
- o prazo é máximo, não obrigatório: revogação, saída do piloto, término da
  finalidade ou solicitação aplicável bloqueiam o uso e antecipam a eliminação,
  ressalvado hold excepcional documentado;
- a alteração não amplia a finalidade, não autoriza treinamento, não inclui
  funcionários de clientes e não amplia o prazo das fotos antigas;
- o aviso e o aceite individual devem ser atualizados para a versão 1.1 antes
  de qualquer novo cadastro ou uso facial real.

A política aprovada permanece imutável. Mudança urgente antes de 24/11/2026
desativa o perfil e interrompe o reconhecimento; a política substituta começa
no vencimento da versão 1.1. Sem renovação, o reconhecimento falha de forma
segura, sem eliminar automaticamente os embeddings ainda dentro da retenção.

Referências imutáveis da versão 1.1:

- base legal: `LGPD-art11-I-consentimento-especifico-piloto-dev-v1.1`;
- aviso: `Aviso-Piloto-Biometrico-FrequenIA-v1.1`;
- decisão/RIPD: `DECISAO-PILOTO-BIOMETRIA-LGPD-v1.1-2026-10-25`;
- relatório técnico: `FASE-33-v1.1-2026-10-25`.

As demais condições da versão 1.0 permanecem. Esta emenda foi confirmada pela
controladora em 25/10/2026; nenhuma linha remota é criada por este documento.
