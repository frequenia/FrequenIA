# Fase 33 — confiabilidade do reconhecimento facial 1:1 e privacidade

Data da validação local: **21/10/2026**.

Este relatório não declara conformidade com a LGPD, base legal válida,
necessidade/proporcionalidade, retenção adequada, precisão, equidade ou SLO de
produção. Não foram usados rostos, embeddings ou dados pessoais reais. Não houve
acesso à AWS, Supabase remoto, produção ou banco do piloto.

## Estado da entrega

| Dimensão | Estado | Evidência/limite |
|---|---|---|
| Implementado localmente | concluído para os defeitos comprovados descritos abaixo | código, regressões unitárias, integrações TLS em PostgreSQL descartável e Flutter |
| Aprovado juridicamente | **não** | depende de controlador/jurídico/DPO; a matriz deste relatório é insumo técnico |
| Validado no piloto | **não** | a Fase 32 permanece parcialmente homologada e sua barreira de banco continua aberta |

### Manifestação da controladora em 22/10/2026

A usuária declarou nesta tarefa: **“eu aprovo a lgpd”**. A manifestação foi
registrada como aprovação geral para prosseguir com a preparação controlada do
piloto, mas não foi convertida automaticamente em uma política biométrica
`aprovada` no banco. A frase, isoladamente, não define os campos imutáveis que a
migration `026` exige nem resolve as decisões abaixo:

- referência da hipótese legal aplicável ao dado biométrico sensível;
- versão e referência documental do aviso aos titulares;
- canal de atendimento efetivamente operacional;
- prazo de retenção e sua justificativa por categoria;
- responsáveis e fluxo de incidentes, decisão sobre RIPD e protocolo de
  calibração/acurácia/equidade.

Até esses dados serem fornecidos e a publicação no piloto ser autorizada em
etapas, o estado jurídico permanece **pendente de formalização** e o
reconhecimento facial deve continuar desabilitado. Nenhuma política, perfil
técnico ou biometria foi criada no banco remoto por esta manifestação.

### Finalidade adicional declarada em 22/10/2026: treinamento futuro

A usuária esclareceu: **“a biometria será guardada e utilizada futuramente para
treinamento”**. A intenção da controladora fica expressa aqui como uma
**finalidade adicional proposta**, distinta da verificação facial 1:1 para
registro de ponto. Ela não equivale à aprovação da coleta, retenção ampliada ou
uso de dados de pessoas para treinamento.

O fluxo implementado hoje armazena no PostgreSQL o *embedding* facial vinculado
ao funcionário e à política de ponto. As fotos de cadastro/verificação são
processadas em memória e não são persistidas pelo fluxo atual. O sistema não
exporta conjuntos de treino nem treina ou ajusta modelos com essas biometrias.
O prazo e a eliminação ainda dependem de uma política aprovada; a possibilidade
de treinamento futuro, por si só, não define um prazo ilimitado.

Antes de utilizar biometria de titulares para treinamento, a controladora deve
definir o objetivo e os dados exatos (foto, embedding ou outros), quem terá
acesso, fundamento jurídico específico para dado sensível, necessidade frente
a dados sintéticos ou anonimizados, prazo por finalidade, aviso anterior ao uso,
direitos dos titulares, segurança, avaliação de impacto e teste da política.
Essa decisão e a implementação terão validação própria. A [orientação da ANPD](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes)
identifica dado biométrico vinculado à pessoa como sensível e informa que o
prazo de tratamento depende da finalidade concreta.

Texto proposto para revisão antes de qualquer cadastro real: “Usamos um modelo
biométrico derivado das fotos para verificar o registro de ponto. As fotos não
são guardadas pelo fluxo atual. Há intenção de uso futuro de dados biométricos
para treinamento, mas essa atividade ainda não ocorre e dependerá de política
própria, informação aos titulares e prazo definido.” Este texto ainda não foi
publicado como aviso válido ao titular.

### Resposta da usuária sobre a política em 22/10/2026

Ao solicitar prazo de guarda, canal de atendimento e referência da hipótese
legal aprovada, a usuária respondeu **“não tenho, mas quero o facial logo”**.
Isso confirma a prioridade do teste facial, mas não fornece os três campos
necessários. Nenhum prazo, e-mail ou fundamento foi presumido. O ensaio técnico
com dados sintéticos pode ser preparado; cadastro/verificação de pessoas no
piloto e treinamento com biometria de titulares continuam pendentes de decisão
específica e aviso adequado.

O `AGENTS.md` lido no início já continha as instruções específicas da Fase 33 e
preservava integralmente a barreira da Fase 32. Não foi necessário afrouxar ou
substituir essas regras. A EC2 não foi consultada nesta fase; portanto, este
relatório não reconfirma seu estado remoto atual e apenas preserva o último
estado `stopped` documentado na Fase 32.

## Referência e preservação do checkout

- branch observada: `codex/aws-pilot-testing`;
- HEAD observado: `e1cd6fed1232c0e32f62920d938cd1ae18da5d95`;
- fingerprint SHA-256 do manifesto ordenado dos 12 arquivos locais de
  implementação/teste da Fase 33:
  `3fc7a196d87a6de5a1166cb71350fa1339f4fab583a25cd3e012dbc636665709`;
- alterações preexistentes preservadas: relatório de publicação modificado,
  documentos não rastreados da Fase 32, `document-assets/`, `output/`, `tmp/` e
  imagens de marca não rastreadas;
- nenhuma migration foi criada ou alterada; a sequência permanece `001`–`026`;
- não houve commit, push, merge ou PR.

## Mapa do fluxo investigado

| Etapa | Backend e autoridade | Mobile | Quiosque/web | Resultado seguro |
|---|---|---|---|---|
| Captura | aceita apenas upload `imagem` JPEG/PNG/WebP, até 5 MiB; cadastro exige 3–5 imagens | câmera frontal preferida, resolução média; arquivo temporário é apagado no `finally` | câmera do navegador via HTTPS, captura JPEG em memória; cadastro mantém 3–5 `Blob`s até envio/reset | cliente não envia identidade, embedding, limiar ou decisão |
| Qualidade | não há classificador explícito de brilho/foco/pose; formato, tamanho, decodificação e face única são os gates atuais | moldura e mensagens orientam posicionamento/iluminação | moldura e instruções equivalentes | nenhuma regra numérica nova foi inventada sem dataset autorizado |
| Detecção | DeepFace/OpenCV com `enforce_detection=True`, alinhamento e exigência de exatamente uma face | imagem enviada ao servidor | imagem enviada ao servidor | zero/múltiplas faces falham fechadas |
| Liveness | MiniFASNet passivo, imagem única, antes do ArcFace; score não é retornado ao cliente | recebe somente motivo controlado | recebe falha genérica não enumerável | spoof simulado não gera marcação; indisponibilidade retorna 503 |
| Embedding | ArcFace `deepface-0.0.99`, 512 dimensões, vetor finito e normalizado; imagem não é persistida | nenhum embedding no app | nenhum embedding no navegador | modelo é carregado tardiamente e falha sem publicar estado parcial |
| Comparação | distância cosseno entre a biometria do funcionário conhecido e o candidato; limiar vem do perfil ativo no servidor | endpoint próprio autenticado | funcionário é resolvido por matrícula dentro do tenant do terminal | exclusivamente 1:1, sem `<=>`, `<->`, galeria ou busca global |
| Tentativa | persiste resultado, motivo, instante PostgreSQL e distância quando houve comparação | sucesso retorna ID opaco da tentativa; marcação ocorre em chamada idempotente separada | tentativa e marcação ficam na mesma transação | falha técnica não é reportada como sucesso |
| Marcação | servidor confirma o evento esperado da jornada e mantém a marcação original imutável | inclui geofence e reaproveita tentativa/chave somente no retry autorizado | usa lock do funcionário e evento esperado | concorrência cria no máximo uma marcação válida |
| `falha_facial` | somente `liveness_reprovado` e `nao_corresponde` contam; cinco tentativas formam ciclo separado | não cria marcação alternativa | não cria marcação alternativa | biometria ausente e falhas técnicas não contaminam o ciclo |

### Diferenças relevantes entre canais

- O mobile verifica primeiro e depois cria a marcação com tentativa e chave de
  idempotência; o quiosque faz verificação e marcação na mesma transação.
- O mobile captura localização antes da foto e apaga o arquivo temporário mesmo
  em erro. O quiosque não executa geofence mobile.
- O quiosque recebe uma matrícula, mas todas as falhas de existência/biometria,
  liveness e match agora retornam o mesmo contrato. O mobile já conhece o vínculo
  pela sessão e pode mostrar `biometria_ausente` ao próprio titular.
- Não há hoje um gate quantitativo autônomo de foco, iluminação, oclusão ou pose.
  Adicioná-lo sem protocolo representativo poderia aumentar falsas rejeições;
  por isso a lacuna foi registrada, não mascarada com números arbitrários.

## Defeitos comprovados e correções

| ID | Evidência anterior | Causa | Correção local | Regressão |
|---|---|---|---|---|
| F33-01 | matrícula inexistente no quiosque retornava 404, enquanto biometria ausente, liveness e mismatch retornavam códigos diferentes | contrato HTTP permitia enumeração a um terminal ativado | resposta/status uniformes (`409`, mensagem genérica), mantendo motivos apenas no banco quando há funcionário conhecido | `test_unknown_registration_and_known_biometric_failures_are_non_enumerable` |
| F33-02 | `/biometria/revogar` fazia `UPDATE` direto e não criava operação idempotente/histórico de ciclo | endpoint legado não usava o serviço da Fase 31 | exige `Idempotency-Key` e chama `transition_biometric` com tenant, ator e motivo técnico | contrato por inspeção + integrações Fases 10/11 via TLS |
| F33-03 | `biometria_ausente` era decisão negativa em 409, mas o serviço Flutter a propagava como exceção | o cliente só interpretava respostas 2xx como decisão facial | o mobile converte exclusivamente esse 409 conhecido em `FaceClockResult.notVerified`; nenhuma marcação é chamada | `409 biometria_ausente vira decisão negativa sem criar marcação` |
| F33-04 | uma chave de idempotência repetida no mesmo tenant validava operação, mas não `funcionario_id`, podendo devolver o ID biométrico de outro vínculo | consulta de reuso omitia o titular da operação | reuso de transição e hold agora exige operação **e** funcionário idênticos; colisão falha com `idempotencia_conflitante` | unitário + PostgreSQL real `test_idempotency_key_cannot_cross_employee_within_tenant` |
| F33-05 | a Fase 31 exigia reconciliação pós-restore, mas não havia executor | lacuna operacional entre histórico append-only e uma linha restaurada divergente | ferramenta tenant-scoped, limitada, `SKIP LOCKED` e dry-run; só repara material quando o último histórico ainda prova `eliminada` | unitários + PostgreSQL real com material artificial ressuscitado |

Nenhum desses ajustes alterou ArcFace, detector, liveness, distância, limiar,
modelo, dimensão ou criação de `falha_facial`. O baseline continua `0.68`.

## Reconciliação pós-restore

`tools/reconcile_biometrics_after_restore.py` compara cada biometria com o último
estado do histórico ainda presente no banco restaurado. O modo padrão apenas
retorna contagens agregadas. Com `--execute`, somente divergências cujo último
estado é `eliminada` têm vetor e referência privada zerados novamente; demais
divergências são `pendentes_manuais` e nunca são reativadas automaticamente.

Limite essencial: se o backup é anterior à eliminação, tanto a linha quanto o
histórico anterior podem parecer ativos. O banco restaurado não consegue inferir
um evento que não está no backup. Antes de habilitar tal restore, o controlador
precisa definir e manter uma fonte autoritativa de tombstones posterior/externa
ao conjunto restaurado, com integridade, acesso, retenção e teste próprios. A
ferramenta local não substitui essa decisão de continuidade.

## Inventário técnico do tratamento biométrico

| Aspecto | Implementado/observado | Pendente de decisão ou validação |
|---|---|---|
| Finalidade | código usa identificador `registro_ponto_1a1` | necessidade, proporcionalidade e hipótese legal aplicável |
| Origem/coleta | câmera web/mobile; cadastro por administrador; verificação pelo próprio vínculo ou terminal | texto do aviso, evidência de ciência e alternativa operacional |
| Imagem bruta | processada em memória no backend; mobile apaga arquivo temporário; web não envia para storage | validação externa de browsers/aparelhos e política para falha de limpeza do SO |
| Embedding | PostgreSQL/pgvector, tenant + funcionário, modelo/perfil/política vinculados | base legal, prazo e controles do banco de homologação/piloto ainda não comprovados |
| Scores | liveness não é retornado nem auditado; distância individual fica apenas em `tentativas_faciais` quando há comparação | retenção/acesso da distância e justificativa de necessidade pelo controlador |
| Transmissão | backend exige conexão PostgreSQL com `sslmode=require`; clientes de produção exigem HTTPS | TLS efetivo do banco do piloto permanece bloqueado pela Fase 32 |
| Acesso | RBAC, vínculo de sessão, terminal ativado, tenant e consulta 1:1 | revisão periódica de acessos e segregação operacional pelo controlador |
| Respostas | status/transparência não selecionam embedding, score ou referência privada | revisão humana do conteúdo do aviso/canal |
| Logs/métricas | eventos biométricos aceitam apenas dimensões de baixa cardinalidade; logs técnicos usam mensagens controladas | política corporativa de acesso, retenção e correlação de incidentes |
| Auditoria | trigger recursivo recusa chaves como imagem, embedding, score, distância, CPF, matrícula, token, caminho e segredo | retenção legal/operacional da auditoria |
| Backup/restore | ensaio local TLS e reconciliador para histórico sobrevivente | tombstones externos, RPO/RTO e restore corporativo aprovados/testados |
| Retenção/hold | política versionada, hold não reabilita, purga dry-run e tenant-scoped | prazo, fundamentos e critérios de hold aprovados |
| Eliminação | vetor e referência ficam nulos; marcações, tentativas, correções e histórico permanecem | escopo jurídico da eliminação e comunicação ao titular |
| Incidente/titular | canal é campo obrigatório de política; runbook técnico existe | responsáveis, SLAs, conteúdo, canal real e decisão de comunicação |

## Verificações de minimização e não vazamento

- respostas de estado não consultam vetor, distância ou referência privada;
- mobile e quiosque não contêm nem enviam embedding/limiar/tenant;
- auditoria recusa chaves sensíveis recursivamente, inclusive em arrays/objetos;
- métricas não aceitam IDs de empresa, funcionário, biometria ou sessão;
- saída da calibração contém somente agregados e
  `automatic_promotion=false`;
- saída da reconciliação contém somente contagens, sem IDs de titulares;
- nenhuma foto, vetor, score individual, dump, segredo ou dataset permaneceu no
  repositório ou no diretório temporário ao final.

## Calibração e métricas agregadas

O harness foi executado com seis distâncias **artificiais**, fora do Git, três
rotuladas `genuine` e três `impostor`, apenas para validar cálculo e sanitização:

| Métrica agregada artificial | Resultado |
|---|---:|
| tamanho | 6 |
| média `genuine` | 0,523333 |
| média `impostor` | 0,73 |
| falsa rejeição no baseline 0,68 | 1/3 (33,33%) |
| falsa aceitação no baseline 0,68 | 1/3 (33,33%) |
| promoção automática | falsa |

Esses números foram escolhidos para atravessar deliberadamente o limiar e testar
o harness. Não medem pessoas, liveness, qualidade, grupos, precisão ou equidade e
não justificam mudar `0.68`. Não houve dataset representativo autorizado.

## Testes realmente executados

| Validação | Resultado em 21/10/2026 |
|---|---|
| descoberta backend `test_*.py` | 359 testes: 260 sucessos, 99 skips opt-in, 0 falhas |
| unidades faciais Fases 9a, 10, 11, 12, 13 e 14 | 38/38 sucessos |
| contratos Fase 31 após correções | 21/21 sucessos |
| regressões unitárias Fase 33 | 3/3 sucessos |
| integração cadastro Fase 10 em PostgreSQL TLS descartável | passou, incluindo cadastro, recadastro, erro facial e revogação governada |
| integração verificação Fase 11 em PostgreSQL TLS descartável | passou, incluindo RBAC/tenant, match, mismatch, liveness, falhas e privacidade |
| PostgreSQL Fase 30 (jornada, ordem, concorrência, imutabilidade) | 12/12 sucessos |
| PostgreSQL Fase 31 (migrations `001`–`026`, estados, hold, eliminação, concorrência) | 13/13 sucessos |
| PostgreSQL Fase 33 (restore parcial e colisão de idempotência) | 2/2 sucessos |
| Flutter focado | 9/9 sucessos |
| `flutter analyze --no-pub` | sem issues |
| `flutter test --no-pub` | 48/48 sucessos |

O PostgreSQL 16/pgvector descartável usou TLS com certificado sintético
autoassinado de curta duração. O contêiner `frequenia-phase33-postgres` foi
parado e removido ao final. Os 99 skips da descoberta são integrações opt-in;
as integrações biométricas e PostgreSQL pertinentes listadas acima foram
executadas separadamente. O run remoto de CI não foi verificado porque não houve
commit/push autorizado.

### Revalidação para publicação em 22/10/2026

Em preparação para a publicação, sem acessar AWS ou Supabase remoto, foram
reexecutadas as integrações contra PostgreSQL 16/pgvector local descartável:

| Validação | Resultado |
|---|---|
| governança biométrica Fase 31 | 13/13 sucessos |
| confiabilidade/recovery Fase 33 | 2/2 sucessos |

O contêiner descartável foi removido ao final. Nenhum rosto, embedding, dado
pessoal real ou segredo foi utilizado.

## Fontes oficiais atuais consultadas

Consultadas em 21/10/2026:

- [Lei nº 13.709/2018 — LGPD, texto compilado](https://planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm), para dados biométricos sensíveis, princípios, hipóteses de tratamento, direitos, RIPD, segurança e incidentes;
- [ANPD — Radar Tecnológico: Biometria e Reconhecimento Facial](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/documentos-tecnicos-orientativos/radar-tecnologico-biometria-anpd-1.pdf), para riscos de erro, discriminação, privacidade e proteção de dados;
- [ANPD — perguntas e respostas sobre RIPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd), página atualizada em 23/09/2026, que atribui a elaboração e decisão de prosseguir ao controlador;
- [Resolução CD/ANPD nº 15/2024 — comunicação de incidente](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/documentos/rcis___anonimizado_final_ocultado_2_parte3.pdf), para avaliação, registro e comunicação de incidentes conforme risco/dano relevante;
- [ANPD — materiais educativos e publicações](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes), para guias de agentes, encarregado e segurança.

As fontes delimitam perguntas e responsabilidades; este relatório não interpreta
nem aprova uma hipótese legal para o contexto de trabalho.

## Matriz de decisões do controlador/jurídico/DPO

| Decisão humana pendente | Insumo técnico disponível | Evidência ainda necessária | Responsável esperado |
|---|---|---|---|
| hipótese legal para dado biométrico sensível | finalidade técnica versionada, 1:1 e minimização | parecer contextual documentado e referência aprovada | controlador/jurídico/DPO |
| necessidade e proporcionalidade no trabalho | não há busca global; falhas são separadas | comparação com alternativas menos intrusivas e impacto laboral | controlador/DPO/RH |
| alternativa em falha, recusa ou impossibilidade | nenhuma marcação sem verificação foi criada | procedimento humano não punitivo, antifraude, contestação e SLA | controlador/RH/DPO |
| prazo de retenção | mecanismo aceita prazo aprovado; purge e hold existem | justificativa por categoria, evento inicial e destino após expiração | controlador/jurídico/DPO |
| aviso e canal de atendimento | versão/canal são campos obrigatórios | texto claro, acessível, momento de exibição e canal operacional | controlador/DPO |
| política de afastamento | `bloquear`, `revogar` ou `preservar` são opções explícitas | decisão por cenário e consistência com vínculo/sessões | controlador/RH/DPO |
| protocolo de calibração | harness agregado, sem promoção automática | dataset autorizado/representativo, grupos, condições, amostragem, critérios e revisão humana | controlador/DPO/equipe técnica |
| RIPD e decisão de prosseguir | inventário, ameaças e salvaguardas deste relatório | contexto organizacional, agentes, escala, titulares, impactos e plano de mitigação | controlador, com consulta ao DPO |
| resposta a incidentes | logs sanitizados e referência à Resolução 15/2024 | papéis, triagem, registro, prazos aplicáveis, comunicação e exercícios | controlador/DPO/segurança |
| tombstones pós-restore | reconciliador para histórico sobrevivente | fonte externa íntegra e teste de backup anterior à eliminação | controlador/continuidade/DPO |
| RPO/RTO | não definidos pelo piloto | objetivos corporativos aprovados e exercício observável | controlador/continuidade |

## Riscos residuais

- liveness passivo de imagem única é experimental e não prova presença física;
- não existe avaliação representativa de foco/iluminação/pose, acurácia ou grupos;
- o baseline `0.68` continua não calibrado;
- diferenças de câmera, compressão, ambiente e população não foram avaliadas;
- armazenamento da distância individual em tentativas exige decisão de
  necessidade, acesso e retenção;
- um backup anterior à eliminação pode ressuscitar material se não houver
  tombstone autoritativo externo;
- o fluxo operacional alternativo para falha/recusa depende do controlador e
  não pode virar bypass técnico;
- testes locais não comprovam configuração, versão, TLS, backup ou restore do
  banco do piloto.

## Critérios para futura homologação externa

1. superar a barreira da Fase 32: banco exclusivo de homologação, vínculo com o
   piloto, TLS efetivo, backup e restauração verificada;
2. decisão formal do controlador/DPO sobre hipótese legal, proporcionalidade,
   aviso, canal, retenção, afastamento, alternativa e incidentes;
3. perfil técnico aprovado sem promoção automática e, se houver avaliação de
   acurácia/equidade, protocolo e dataset formalmente autorizados fora do Git;
4. dispositivos e navegadores representativos, condições de captura definidas e
   somente participantes/dados autorizados;
5. execução externa de cadastro, mobile e quiosque, incluindo câmera, qualidade,
   liveness, match/mismatch, indisponibilidade, timeout e concorrência;
6. confirmação de isolamento tenant/RBAC, não enumeração, `falha_facial`, jornada,
   geofence, marcação original, correções, anexos e visão efetiva;
7. exercício de bloqueio, revogação, desligamento, hold, eliminação, restore e
   tombstone sem reabilitar material;
8. revisão sanitizada de respostas, logs, auditoria, métricas e artefatos;
9. rollback operacional e encerramento comprovados, sem extrapolar resultados do
   piloto para produção.

## Conclusão

A implementação local da Fase 33 está concluída para os defeitos comprovados e
suas regressões. A aprovação jurídica não foi realizada e a validação no piloto
não foi executada. A Fase 32 continua **parcialmente homologada**.

## Retomada de 23/10/2026 — minuta para fotos e aceite individual

Esta seção é **minuta de trabalho**, não política aprovada, aviso publicado ou
autorização de teste. A operadora quer manter o Supabase atual e declarou que
nele há biometria real, inclusive sua e de outra pessoa. Em 23/10, escolheu
preservar as fotos já existentes até a revisão do piloto, sem configurar
apagamento automático agora, e registrar o aceite específico de cada novo
participante por **termo ou e-mail individual guardado privadamente**. Depois
esclareceu que deseja incluir mais pessoas e manter o uso ativo após a revisão
de 60 dias. Em resposta posterior, especificou **testadores externos**, sem
funcionários nesta liberação e **sem treinamento de IA agora**. Declarou que
os testadores externos serão somente adultos capazes, com participação
voluntária e possibilidade de recusa sem prejuízo; isso ainda não foi verificado
individualmente. Propôs o prazo máximo de **365 dias desde cada cadastro para o
embedding** e de **365 dias desde o início do piloto para as fotos anteriores**,
ambos sujeitos à revisão jurídica e ainda não implementados como vencimento
efetivo. A data de início do piloto deve ser registrada antes de calcular o
vencimento das fotos. O comprovante individual de cada aceite ainda precisa
ser obtido; a concordância verbal anterior não foi tratada como comprovante
retroativo. Não houve autorização para apagar as fotos ou embeddings agora.
Segundo esclarecimento da operadora, o Supabase atual contém os embeddings e
os links das fotos; os arquivos originais estão no Cloudinary. Essa localização
foi declarada, não verificada por abertura de imagens ou links. Um dump lógico
do Supabase preserva somente os registros/referências do banco, **não** os
arquivos do Cloudinary. A proteção, disponibilidade, titularidade e eventual
eliminação das fotos devem ser verificadas separadamente na conta Cloudinary.

### Texto-base a completar e submeter ao controlador/jurídico

> O FrequenIA propõe usar imagens do rosto exclusivamente para cadastrar e
> verificar, de forma 1:1, a pessoa previamente identificada durante um piloto
> técnico. A captura atual é processada para gerar um modelo biométrico
> (*embedding*); o fluxo atual não salva novas fotos de cadastro ou verificação.
> O banco existente contém referências a fotos anteriores armazenadas no
> Cloudinary, conforme informação da operadora; acesso, proteção e prazo ainda
> serão conferidos sem abrir as imagens. Não há busca facial
> global nem treinamento de IA autorizado nesta minuta. Participar deve ser
> opcional e a recusa ou falha deve ter alternativa humana sem prejuízo.
> Para dúvidas e direitos sobre os dados, o canal proposto é
> `frequenia@gmail.com` (funcionamento ainda não testado). Antes de qualquer
> novo teste, informar a identidade do controlador, os operadores, o local de
> armazenamento, quem acessa, a hipótese jurídica aprovada, os prazos separados
> de fotos e embeddings, a forma de revogação/eliminação e a versão deste aviso.

O aceite por termo/e-mail deve identificar a **versão final do aviso**, a
finalidade 1:1, a pessoa titular, a data e uma manifestação expressa e destacada;
o comprovante fica em local privado, fora do Git, e no sistema entra apenas uma
referência não sensível. Treinamento futuro, se pretendido, exigirá avaliação,
aviso e escolha separados; este aceite não o abrangerá. Para participantes com
vínculo de trabalho, jurídico/DPO deve avaliar a liberdade efetiva da escolha e
qual hipótese do art. 11 é adequada antes de usar consentimento como fundamento.

### Minuta histórica de convite e resposta individual — substituída pela v1.1

O texto abaixo registra a proposta anterior de 365 dias e não deve mais ser
usado. O aviso aprovado e o texto atual de aceite estão em
`docs/AVISO_PILOTO_BIOMETRICO_V1_1.md`.

Assunto proposto: `FrequenIA — convite voluntário para teste facial 1:1`.

> Convidamos você, pessoa adulta, a participar voluntariamente do piloto de
> reconhecimento facial 1:1 do FrequenIA. A recusa não causa prejuízo; haverá
> alternativa humana para realizar o teste sem reconhecimento facial. A imagem
> capturada pelo fluxo novo gera um embedding, mas não é guardada como foto por
> esse fluxo. Se já houver foto sua vinculada ao sistema, seu tratamento será
> descrito separadamente antes do aceite. O piloto será revisto após 60 dias;
> a proposta de guarda máxima é de 365 dias desde o cadastro para o embedding
> e, para fotos anteriores, 365 dias desde o início registrado do piloto.
> Esses prazos e o modo de eliminação ainda dependem de aprovação e implementação.
> Seus dados não serão usados para treinar IA nesta autorização. Controlador:
> [identificação a preencher]. Canal de atendimento e revogação proposto:
> frequenia@gmail.com [confirmar funcionamento]. Leia o aviso final versão
> [versão] antes de decidir.

Resposta expressa proposta, a ser enviada **somente após** o aviso final e as
salvaguardas aprovados: `Li o aviso FrequenIA versão [versão] e aceito
voluntariamente o uso dos meus dados faciais exclusivamente para cadastro e
verificação 1:1 neste piloto. Sei que posso recusar ou solicitar revogação pelo
canal informado. Não autorizo treinamento de IA por este aceite.` Não preencher
ou coletar resposta em nome da pessoa. Guardar cada mensagem/termo em repositório
privado com acesso restrito e registrar apenas data, versão e referência interna
não sensível no controle do piloto.

Antes de enviar convites: identificar formalmente o controlador; aprovar a
hipótese do art. 11 e a necessidade/proporcionalidade; confirmar alternativa
humana, canal e resposta a incidentes; decidir RIPD; aprovar prazos e fluxo de
eliminação; definir a data inicial; validar armazenamento e acesso às fotos
anteriores; e testar tecnicamente bloqueio no vencimento e restauração sem
reativação. O aceite não substitui essas etapas.

### Lacuna técnica de duração

O resolvedor local de verificação 1:1 agora compara `created_at` com
`retencao_dias` da política vigente usando `statement_timestamp()` do
PostgreSQL. Se o prazo venceu ou a data é nula, responde
`biometria_expirada`; a consulta não devolve o embedding vencido à aplicação.
Isso cobre as rotas web/mobile e quiosque que usam o resolvedor, **mas não
elimina automaticamente** a linha, o vetor armazenado ou fotos antigas.
`purge_eligible` continua restrito a `exclusao_pendente`; não foi expandido
para apagar dados ativos sem política e confirmação operacional. Também não há
vínculo técnico entre as referências de fotos anteriores e a data inicial do
piloto, nem controle de eliminação dos arquivos originais no Cloudinary. A
revisão aos 60 dias não é vencimento: a operadora quer manter o uso ativo.
Antes de habilitar o reconhecimento com pessoas reais, aprovar os dois prazos
de 365 dias, configurar a política com o prazo efetivo, registrar o início do
piloto, verificar a proteção dos originais no Cloudinary sem abri-los,
implementar o fluxo de eliminação auditável em ambos os serviços e testar
revogação/restore e o bloqueio em PostgreSQL isolado. Em 23/10/2026, o teste local com PostgreSQL/pgvector 16
descartável no Docker do WSL passou: a biometria sintética dentro do prazo foi
retornada, e a vencida recebeu `biometria_expirada`; a suíte de integração da
Fase 31 passou 14/14. O contêiner temporário foi encerrado. A suíte unitária
local passou 382 testes, 102 skips. Nenhuma migration, consulta remota ou
eliminação foi feita nesta retomada.

### Situação em 24/10/2026

O backup cifrado do banco atual foi criado e o schema `public` com seus dados
restaurou em PostgreSQL local isolado; o restore integral dos schemas internos
do Supabase falhou por extensão ausente na imagem local. Não se consultou nem
exibiu biometria real. Os testes unitários focados da Fase 33 passaram (5
executados, 2 integrações opt-in ignoradas). Isso não é validação facial no
piloto nem decisão LGPD: os oito itens de aprovação humana e os aceites
individuais documentados ainda precisam ser registrados. O facial permanece
desabilitado e a migration `026` não foi aplicada remotamente.

Em 24/10/2026, após a sessão técnica AWS, a operadora reafirmou sua aprovação
geral da LGPD e pediu a ativação imediata. Permanecem documentados como
decisões propostas para o piloto: verificação 1:1 de adultos voluntários,
sem treinamento agora, revisão em 60 dias, guarda proposta de até 365 dias
para embeddings e fotos anteriores em marcos distintos, e canal
`frequenia@gmail.com`. A manifestação geral não foi convertida em aceite
específico de cada titular nem em decisão formal sobre hipótese jurídica,
RIPD, resposta a incidentes, eliminação no Cloudinary e calibração. A imagem
nova e a migration `026` ainda não estão ativas; portanto não há uma chave
simples de ativação facial nesta etapa.

Na sequência, a operadora confirmou que **existem** termos ou e-mails
individuais de aceite guardados privadamente. Esta é uma declaração da
controladora; o assistente não recebeu nem examinou documentos, nomes,
versões do aviso ou a correspondência entre cada aceite e cadastro. A
confirmação reduz a lacuna documental, mas não comprova sozinha os demais
itens de decisão e implementação pendentes.

Diagnóstico posterior, somente de catálogo e conduzido privadamente pela
operadora em 24/10/2026: a `026` já apresenta os cinco grupos estruturais
esperados (tabelas, colunas, índices, gatilhos e restrições). Nenhuma migration
foi aplicada nesta sessão. Isso corrige a indicação anterior de que a `026`
estaria ausente no banco; não comprova origem, semântica de dados, implantação
da imagem ou prontidão jurídica. Não reaplicar a `026` e manter o facial
desabilitado enquanto as decisões e controles restantes não forem concluídos.

### Validação técnica no piloto em 25/10/2026

O hotfix foi publicado e executado no runtime ARM64 com o ID esperado. App,
dispatcher, worker, Caddy e ClamAV ficaram ativos sem reinícios; HTTPS,
`/health` e `/ready` passaram. Um diagnóstico de saída estritamente booleana
confirmou o projeto Supabase esperado, `sslmode=verify-full`, CA legível e TLS
cliente ativo, sem expor conexão, segredo ou dado pessoal. A EC2 foi encerrada
pelo controlador e confirmada `stopped`.

Essa evidência remove as pendências técnicas de imagem, vínculo e TLS, mas não
cria uma política biométrica aprovada, não ativa perfil técnico, não valida
aceites individuais e não substitui os oito registros humanos da decisão do
controlador. Não houve teste facial real ou autenticado nesta sessão.

Em 25/10/2026, a operadora escolheu como hipótese para o piloto com
desenvolvedores adultos voluntários o consentimento específico e destacado do
art. 11, I, limitado a cadastro e verificação 1:1 e sem treinamento. A escolha
foi registrada, mas a expressão “os desenvolvedores” ainda não identifica a
pessoa natural ou jurídica que decide a finalidade e os elementos essenciais
do tratamento. A ativação continua pendente dessa identificação e dos demais
registros humanos da minuta.

Posteriormente, a responsável aprovou em nome da `Equipe FrequenIA` o pacote
`DECISAO-PILOTO-BIOMETRIA-LGPD-v1.0-2026-10-25`, limitado aos desenvolvedores
adultos voluntários, com consentimento específico, finalidade 1:1, alternativa
humana, revisão em 60 dias, retenção máxima de 365 dias, canal informado,
resposta a incidentes, RIPD simplificado e protocolo funcional sem alteração do
limiar `0.68`. Essa decisão não substitui os aceites individuais nem autoriza
automaticamente a escrita remota da política, a ativação do perfil ou o teste
com pessoas reais; cada operação permanece sujeita a confirmação própria.

Foi preparado o operador local
`infra/aws/scripts/biometric-governance-operator.ps1`, com ações separadas
`policy`, `profile` e `readiness`. Ele fixa o HTTPS do piloto, solicita CPF e
senha como `SecureString` somente no terminal privado da operadora, mantém
cookies/tokens em memória e emite apenas indicadores sanitizados. A política
preparada usa retenção de 365 dias e as referências imutáveis da decisão v1.0;
o perfil usa ArcFace/deepface 0.0.99, 512 dimensões, distância cosseno e limiar
inalterado `0.68`. O parser PowerShell passou e os 12 testes de infraestrutura
passaram. O operador ainda não foi executado e nenhuma linha remota foi criada.

Na preparação da primeira escrita, foi identificado que política e perfil eram
criados sem data final e que não havia endpoint de rollback para desativar o
perfil. A operação remota foi interrompida antes de criar qualquer linha. A API
agora exige `vigencia_fim` para ambos (25/10/2027 no piloto) e oferece
desativação autenticada, transacional, com lock e auditoria. O operador ganhou
a ação separada `disable`. Passaram 25 testes de governança, 12 de
infraestrutura, validação de sintaxe e smoke ARM64 isolado. A candidata local
resultante tem tag `frequenia:pilot`, config `sha256:76f97392…e7de9c` e pacote
SHA-256 `d548ec844d4965ec1fa663bfb3fdad8cd7e945679940a6a426c4c4f04b4540cf`.
Ela ainda não foi enviada nem selecionada no piloto.

Com confirmação específica, a candidata de rollback foi enviada a uma nova
chave imutável do bucket privado. A verificação remota confirmou 920.675.134
bytes, SSE-S3/AES256 e metadado SHA-256 igual a
`d548ec844d4965ec1fa663bfb3fdad8cd7e945679940a6a426c4c4f04b4540cf`.
O ponteiro, a EC2 e o banco permaneceram inalterados.

Com confirmação específica posterior, o ponteiro foi trocado
condicionalmente para a candidata de rollback; a leitura remota confirmou a
chave exata e a EC2 permaneceu `stopped`. Banco, política, perfil e dados
biométricos não foram alterados. O próximo boot controlado ainda precisa
validar a imagem antes da primeira escrita de governança.

O boot controlado posterior validou a candidata com o config esperado
`sha256:76f97392…e7de9c`. Cinco containers ficaram ativos com zero reinícios;
HTTPS, `/health` e `/ready` passaram. A rota de rollback existia e rejeitou a
requisição sem autenticação com 401, sem mutação. A EC2 foi encerrada e
confirmada `stopped` (48.369/144.000 segundos). A imagem está publicada e
validada; política, perfil e reconhecimento facial ainda não foram ativados.

Antes da primeira escrita remota, o ciclo de governança foi exercitado em um
PostgreSQL local descartável exclusivamente com fixtures sintéticas: criação
de política e perfil com vigência limitada, readiness positivo, desativação
autenticada do perfil e readiness negativo após rollback. A suíte concluiu
15/15 testes; o container descartável foi removido e nenhum dado do Supabase
foi acessado ou alterado.

Emenda v1.1 aprovada em 25/10/2026: a controladora definiu a primeira vigência
da política e do perfil até 24/11/2026 e ampliou a retenção dos embeddings para
no máximo 1.825 dias desde o cadastro. A justificativa operacional é permitir
avaliação longitudinal e reduzir recadastros, limitada aos desenvolvedores
adultos voluntários. A revisão ocorrerá em 30 dias; sem nova versão, o
reconhecimento para de forma segura. Permanecem
eliminação antecipada, alternativa humana, limiar `0.68` e proibição de
treinamento. Fotos antigas não tiveram o prazo ampliado. Aviso e aceite passam
à versão 1.1 e devem ser obtidos antes do uso real. O operador privado foi
atualizado para `pilot-dev-1.1.0`, retenção `1825` e vigência encerrada em
24/11/2026. A validação concluiu 12/12 testes de infraestrutura, 25/25 de governança,
15/15 de integração PostgreSQL e parser PowerShell. Nenhuma linha remota foi
criada nesta atualização.

A revisão posterior confirmou novamente todo o conjunto já com a vigência de
30 dias: 12/12 testes de infraestrutura, 25/25 de governança, parser PowerShell
e 15/15 testes PostgreSQL. O banco sintético foi removido ao final. A EC2 e o
banco Supabase permaneceram inalterados.

Com confirmação específica posterior, a operadora executou o operador privado
e informou somente `policy_created=1`, versão `pilot-dev-1.1.0` e retenção
`1825`. A política imutável foi criada no banco atual, com vigência até
24/11/2026. Nenhuma foto, embedding ou linha pessoal foi consultada; o perfil
técnico ainda não foi criado e o reconhecimento permanece desabilitado.

Após confirmação específica separada, a operadora criou o perfil técnico ativo
e informou somente `profile_created=1`, versão `pilot-dev-1.1.0` e limiar
`0.68`. O piloto passou a ter política e perfil vigentes até 24/11/2026. Nenhum
segredo, foto, embedding ou dado pessoal foi exibido ao assistente; readiness e
teste real ainda permaneciam pendentes neste ponto.

A consulta autenticada posterior retornou somente os indicadores sanitizados
`readiness_policy=1`, `readiness_profile=1` e `readiness_compatible=1`. A
governança técnica está pronta e o reconhecimento pode seguir para teste 1:1
somente com desenvolvedor que aceitou o aviso v1.1, após confirmação específica.

Após recadastro autorizado na política/perfil v1.1, o teste real pelo APK
avançou pela verificação facial e chegou ao motor de jornada. A marcação não foi
criada porque o vínculo não possuía jornada configurada; o aplicativo exibiu
`sem_jornada` e conflito. Esse resultado comprova o reconhecimento 1:1 no fluxo
real, mas não homologa o registro de ponto completo. Nenhuma foto foi enviada
ao assistente e nenhum dado pessoal foi registrado neste relatório.

Em seguida, a operadora informou ter preparado uma escala temporária para
26/10/2026. A repetição realizada ainda em 25/10/2026 permaneceu bloqueada por
`sem_jornada`, comportamento esperado porque o snapshot diário dessa data já
havia sido materializado e não pode ser reescrito. A validação ponta a ponta da
marcação ficou, portanto, pendente para 26/10/2026; o reconhecimento facial em
si permanece validado. A EC2 foi encerrada ao fim da sessão e confirmada em
`stopped`, sem trava de custo, com 52.557/144.000 segundos utilizados.

Em 26/10/2026, após nova confirmação específica, o piloto respondeu em HTTPS
com `/health` e `/ready` em `200`. A participante previamente autorizada
executou o fluxo no APK e informou somente que o reconhecimento concluiu e o
ponto foi registrado corretamente. Essa evidência homologa o percurso real
reconhecimento 1:1 → jornada vigente → persistência da marcação, sem exposição
de foto, embedding, matrícula ou linha pessoal ao assistente.

O teste separado do quiosque inicialmente falhou durante o encerramento da
primeira sessão com `Failed to fetch`. Em nova sessão saudável, com os mesmos
endpoints em `200`, o quiosque retornou erro genérico de registro. A análise
local identificou que `_record_attempt` usava acesso posicional em um
`RealDictCursor`; o hotfix passou a ler o campo `id` por nome. Os 7 testes do
quiosque e 3 testes de confiabilidade biométrica passaram com fixtures
sintéticas. A imagem AWS ainda não contém esse hotfix: o build ARM64 local foi
interrompido por falha do Docker/WSL e nenhuma publicação remota ocorreu.

Em 13/11/2026, o hotfix foi empacotado, enviado a uma chave imutável do bucket
privado e selecionado por troca condicional do ponteiro. O runtime ARM64
carregou o config esperado `sha256:50a7eee2…772b59` e confirmou a correção no
container. Um primeiro boot encontrou o projeto Free do Supabase indisponível;
a falha sanitizada do pooler foi resolvida após a operadora despausar o mesmo
projeto `xoof…esgx/main`, sem troca de banco ou plano.

No boot seguinte, `db_connect=1`, os cinco containers ficaram ativos, e HTTPS,
`/health` e `/ready` responderam 200. Após nova confirmação específica, uma
desenvolvedora voluntária abrangida pelo aviso `pilot-dev-1.1.0` realizou o
teste 1:1 no quiosque e informou que o reconhecimento funcionou. O assistente
não recebeu foto, embedding, matrícula, resultado individual ou linha pessoal.
A EC2 foi encerrada pelo controlador e confirmada `stopped`; a política e o
perfil continuam sujeitos ao vencimento de 24/11/2026.
