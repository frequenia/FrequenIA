# Aviso Piloto Biométrico FrequenIA v1.1

Data: 25/10/2026
Controlador operacional do piloto: `Equipe FrequenIA`
Canal para dúvidas, direitos e revogação: `frequenia@gmail.com`

## Finalidade e participação

O piloto usa reconhecimento facial somente para cadastrar e verificar, de
forma 1:1, uma pessoa previamente identificada no teste de registro de ponto.
A participação é voluntária, limitada a desenvolvedores adultos, e pode ser
recusada ou revogada sem prejuízo. Em recusa, falha ou indisponibilidade, deve
ser oferecida conferência humana e forma alternativa de registro.

Este aceite não autoriza busca facial global, identificação de desconhecidos,
compartilhamento para finalidade própria de terceiros, treinamento de IA ou
inclusão de funcionários de clientes.

## Dados e tratamento

Durante o cadastro ou a verificação, a imagem capturada é processada para gerar
ou comparar um modelo matemático do rosto, chamado *embedding*. O fluxo novo
não guarda a captura como uma nova foto. São tratados o embedding, referências
de governança, resultado técnico e registros de auditoria sem conteúdo facial.

O processamento usa a infraestrutura contratada para o piloto, incluindo AWS
e Supabase. Referências a fotos antigas que já existam no Cloudinary possuem
tratamento e prazo próprios; a versão 1.1 não amplia esse prazo.

## Hipótese e prazo

A hipótese escolhida para este piloto é o consentimento específico e destacado
para dado biométrico sensível, conforme art. 11, I, da LGPD.

A primeira política e o perfil técnico vigoram até 24/11/2026. Cada embedding
pode ser mantido por no máximo 1.825 dias desde o cadastro. Esses são prazos
máximos, não obrigatórios. A necessidade será revista em 30 dias; a continuidade
do reconhecimento exige uma nova versão da política e do perfil.

Revogação, saída do piloto, fim da finalidade ou solicitação aplicável bloqueiam
o uso e antecipam a eliminação, ressalvado somente um *hold* excepcional,
documentado e legalmente justificável. Restaurações de backup não podem reativar
material eliminado.

## Direitos e incidentes

A pessoa pode solicitar confirmação do tratamento, informações, correção de
dados cadastrais, revogação, bloqueio ou eliminação aplicável pelo canal
`frequenia@gmail.com`. Uma suspeita de incidente deve bloquear o fluxo afetado,
restringir o acesso e ser avaliada e comunicada conforme as regras aplicáveis.
Fotos, embeddings e segredos não devem ser enviados por e-mail.

## Aceite individual sugerido

> Li o Aviso Piloto Biométrico FrequenIA v1.1. Aceito voluntariamente o uso do
> meu dado facial exclusivamente para cadastro e verificação 1:1 neste piloto,
> com retenção do embedding por no máximo 1.825 dias desde o cadastro. Sei que
> posso recusar ou revogar pelo canal informado, sem prejuízo e com alternativa
> humana. Este aceite não autoriza treinamento de IA.

O termo ou e-mail deve identificar a pessoa, a versão `1.1` e a data. O
comprovante deve permanecer em repositório privado de acesso restrito; não deve
ser anexado ao Git nem enviado ao assistente.
