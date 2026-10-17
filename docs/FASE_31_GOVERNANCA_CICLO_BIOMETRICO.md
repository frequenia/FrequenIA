# Fase 31 — Governança e ciclo de vida biométrico

Data da validação local: 2026-10-16. Este documento não declara conformidade
LGPD, base legal válida, retenção adequada ou precisão de produção.

## Decisão arquitetural

O PostgreSQL é a autoridade de política, perfil técnico e ciclo. Cadastro e
verificação 1:1 resolvem política aprovada e perfil ativo no servidor. O cliente
não informa tenant, pessoa, embedding, modelo, limiar ou decisão de liveness.
Fotos continuam processadas em memória. Não existe pesquisa facial global.

A migration `026_biometric_governance_lifecycle.sql` adiciona política e perfil
versionados, estados `ativa`, `bloqueada`, `revogada`, `exclusao_pendente` e
`eliminada`, hold formal, idempotência e histórico append-only. Eliminação exige
vetor e referência privada nulos; demais estados preservam o vetor para prova e
retenção. Registros legados são preservados, sem receber política inventada, e
precisam de recadastro governado para voltar a verificar.

Desligamento usa uma transação para travar vínculo, revogar biometria, calcular
elegibilidade pela política vinculada, revogar todas as sessões e auditar. Uma
falha reverte tudo. Reativação não restaura sessões ou vetores. Afastamento é
controlado por `BIOMETRIC_AWAY_POLICY` (`bloquear`, `revogar`, `preservar`).

## Política, transparência e perfil técnico

Política armazena apenas referência controlada de base legal, versão de aviso,
finalidade, vigência, retenção, canal e ID técnico do aprovador. Não armazena
parecer ou consentimento presumido. Perfis registram ArcFace/modelo, dimensão,
métrica, limiar, liveness, vigência e referência de relatório. O `0.68` segue
identificado como baseline não calibrado.

Web e Flutter reutilizam o perfil e exibem estado, finalidade, aviso, retenção e
atendimento. Vetor, score e referência privada não são expostos.

## Retenção, hold, eliminação e continuidade

`tools/purge_biometrics.py` é dry-run por padrão, tenant-scoped, limitado e usa
`FOR UPDATE SKIP LOCKED`. Hold válido suspende eliminação sem autorizar uso.
`--execute` zera vetor/referência e preserva metadados/histórico. O estado
autoritativo `eliminada` prevalece após restore; reconciliação deve remover
qualquer material ressuscitado antes de habilitar o ambiente restaurado.

## Calibração e observabilidade

`tools/calibrate_biometrics.py` recusa dataset dentro do Git ou sem autorização
explícita. A saída contém apenas agregados e `automatic_promotion=false`.
Métricas/eventos aceitam somente dimensões de baixa cardinalidade. Auditoria
recusa chaves sensíveis também dentro de objetos/arrays aninhados.

## Fontes oficiais consultadas

Consultadas em 2026-10-16:

- [Lei nº 13.709/2018 — LGPD, texto compilado](https://planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm);
- [ANPD — Biometria e reconhecimento facial](https://www.gov.br/anpd/pt-br/assuntos/noticias/biometria-e-tema-do-segundo-volume-da-serie-radar-tecnologico);
- [ANPD — Tomada de subsídios sobre dados biométricos](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-abre-tomada-de-subsidios-sobre-tratamento-de-dados-biometricos);
- [ANPD — Comunicação de incidente de segurança](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis);
- [Resolução CD/ANPD nº 15/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/documentos/rcis___anonimizado_final_ocultado_2_parte3.pdf).

O código apenas apoia a decisão do controlador. Comunicação externa permanece
humana; nenhum prazo jurídico foi codificado.

## Matriz dos 70 critérios

| Critérios | Evidência principal |
|---|---|
| 1–10 | `test_phase31_biometric_governance.py` (contratos) e testes PG de resolução, sobreposição, limiar, upgrade e vínculo política/perfil |
| 11–15 | regressões Fases 10/15, cadastro governado e corrida real com duas conexões, lock do vínculo e índice parcial de uma ativa |
| 16–25 | testes PG de compatibilidade, bloqueio/revogação, constraints de material e transições idempotentes |
| 26–35 | teste PG de desligamento/sessões/rollback, política de afastamento e locks de verificação/cadastro |
| 36–41 | política vinculada, retenção sem default, hold/cancelamento e histórico append-only |
| 42–50 | dry-run, eliminação, repetição, concorrência `SKIP LOCKED`, preservação de tabelas e observabilidade |
| 51–60 | endpoints pessoais/admin, RBAC, 404 tenant-scoped, auditoria recursiva e UI web/Flutter |
| 61–64 | harness agregado, runbook oficial e dimensões sanitizadas |
| 65–67 | instalação `001`–`026`, upgrade `001`–`025 → 026` e suíte PG real |
| 68 | descoberta backend completa e suítes dedicadas das Fases 25–31 |
| 69–70 | `flutter analyze` e `flutter test` |

O detalhamento individual é mantido em `docs/FASE_31_MATRIZ_70_CRITERIOS.md`.

## Resultados de validação

Resultados locais em 2026-10-16, sem serviços ou credenciais de produção:

| Validação | Resultado |
|---|---|
| Descoberta backend `python -m unittest discover -s tests -p "test_*.py" -v` | 353 testes: 256 sucessos, 97 skips opt-in explícitos, 0 falhas |
| Contratos/unitários específicos da Fase 31 | 20/20 sucessos |
| PostgreSQL Fase 25 | 31/31 sucessos |
| PostgreSQL/anexos Fase 26 | 17/17 sucessos |
| PostgreSQL/S3/ClamAV Fase 27 | 8/8 sucessos |
| PostgreSQL/SQS Fase 28 | 9/9 sucessos |
| PostgreSQL/continuidade Fase 29 | 7/7 sucessos |
| PostgreSQL/jornada Fase 30 | 12/12 sucessos |
| PostgreSQL/biometria Fase 31 | 13/13 sucessos, incluindo instalação limpa, upgrade e duas conexões concorrentes |
| Contratos de CI | 5/5 sucessos; etapa opt-in da Fase 31 declarada |
| Contratos de configuração/secret hygiene | 5/5 sucessos |
| `flutter analyze` | sem issues (8,3 s na execução final) |
| `flutter test` | 48/48 sucessos |

Na descoberta padrão, as integrações externas ficam explicitamente ignoradas
sem as variáveis opt-in. Nas execuções dedicadas elas foram habilitadas e não
houve skip. PostgreSQL 16/pgvector, Moto S3/SQS e ClamAV foram usados apenas em
contêineres descartáveis locais. Os contêineres
`frequenia-phase31-postgres`, `frequenia-phase31-moto` e
`frequenia-phase31-clamav` foram removidos ao final; o diretório temporário
esperado foi conferido sob o diretório temporário do sistema e já não existia.
O run remoto do GitHub Actions permanece
pendente porque não houve commit ou push autorizado.

Houve duas limitações de ambiente diagnosticadas durante a homologação: o
sandbox bloqueou inicialmente a conexão TCP local, exigindo a execução
autorizada fora dele; e o Windows não possuía `pg_dump`/`pg_restore`, por isso o
exercício da Fase 29 utilizou os binários do próprio contêiner PostgreSQL
descartável, sem interpolação de credenciais na linha de comando. As repetições
finais passaram.

## Decisões pendentes do controlador/jurídico/DPO

- base legal e referência documental por finalidade;
- retenção adequada e condições de hold;
- conteúdo, responsável e canal do aviso;
- política de afastamento de produção;
- protocolo/dataset de calibração e eventual análise por grupos;
- avaliação e comunicação de incidente conforme norma vigente.

## Limitações e Fase 32

Homologação externa, execução remota da CI, calibração representativa, validação
jurídica e teste de restore corporativo permanecem pendentes. Recomenda-se na próxima fase: console
operacional de políticas/perfis com dupla aprovação, reconciliação pós-restore
do estado eliminado, exercícios de incidente e calibração autorizada.

Não houve commit, push, merge, PR, deploy, provisionamento cloud, consulta a
conta AWS ou acesso à produção.
