# Runbook — incidente biométrico

Este runbook prepara evidência e coordenação humana. Ele não comunica ANPD ou
titulares, não define base legal e não substitui decisão do controlador/DPO.

## Detecção e sinais

- aumento agregado de verificações bloqueadas ou incompatíveis;
- política/perfil em `not_ready`;
- acessos anômalos, exposição suspeita ou fila de eliminação envelhecida;
- relato recebido pelo canal formal da política vigente.

Preserve IDs técnicos, versões de política/perfil, timestamps do PostgreSQL,
logs sanitizados e trilha append-only. Não copie vetor, foto, score individual,
CPF, matrícula, token ou referência privada para ticket, chat ou métrica.

## Contenção

1. Acione o responsável humano definido na política e classifique o escopo.
2. Use bloqueio tenant-scoped e idempotente quando autorizado.
3. Revogue sessões/vínculos comprometidos pelo serviço transacional.
4. Não reative vetor antigo, não reduza limiar, não ignore liveness e não use
   `falha_facial` como atalho de incidente.
5. Hold formal pode preservar evidência, mas nunca restaura uso operacional.

## Diagnóstico e avaliação humana

- valide política, perfil, modelo, liveness e período afetado;
- diferencie indisponibilidade, incompatibilidade e possível exposição;
- confirme se há risco ou dano relevante com o controlador/jurídico/DPO;
- consulte a [LGPD](https://planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm)
  e a página oficial vigente da [ANPD sobre comunicação de incidente](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

Nenhum prazo regulatório é hardcoded neste runbook. Antes de comunicar, o
responsável deve confirmar fonte, prazo, legitimidade e conteúdo vigentes.

## Recuperação e validação

1. Corrija a causa em ambiente isolado e execute regressões biométricas.
2. Cadastros incompatíveis exigem recadastro; nunca migre vetor sem decisão de
   compatibilidade versionada e testada.
3. Confirme que bloqueada/revogada/exclusão pendente/eliminada não verifica.
4. Confirme que sessões revogadas continuam inválidas e que reativação do
   vínculo não ressuscita biometria.
5. Valide que marcações, tentativas, correções e `falha_facial` permaneceram.

## Comunicação e pós-incidente

Comunicação externa exige decisão e execução humana autorizada. Preserve a
decisão, fonte normativa consultada, timestamp, evidência sanitizada e versão
da política. Registre ações corretivas, revise perfil/política e calibre apenas
com dataset autorizado. É proibido anexar material biométrico bruto ao relato.
