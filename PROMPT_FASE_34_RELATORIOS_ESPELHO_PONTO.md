# Prompt — Fase 34: relatórios e espelho de ponto

Implemente a Fase 34 do FrequenIA **somente em ambiente local e descartável**, seguindo `AGENTS.md`. O objetivo é completar os requisitos RF-046–RF-050 do plano inicial: relatório de marcações por funcionário, visões de atrasos/ausências/solicitações, espelho de ponto e exportação PDF, Excel/XLSX, CSV e Word para RH. Não tratar esta fase como cálculo de folha ou homologação trabalhista.

## Contexto e limites

- Leia `C:\Users\lavin\Downloads\FrequenIA_Especificacao_e_Plano_v1.md`, os relatórios das Fases 25, 30, 32 e 33, `services/effective_timekeeping.py`, `services/daily_journey.py`, `routes/timekeeping.py`, telas de gestão e testes existentes. Inspecione `git status --short` e preserve todas as alterações preexistentes.
- Já existem `/api/gestao/pontos` e `/exportar-pontos` em CSV/PDF/DOCX, alimentados pela visão efetiva. A apresentação atual agrupa pelo dia civil de São Paulo; verifique e corrija apenas as divergências demonstradas em jornadas noturnas, cuja autoridade é a `data_operacional` do snapshot da Fase 30.
- A Fase 32 permanece parcialmente homologada. Não acessar AWS, Supabase remoto, produção, dados reais ou o banco do piloto; não publicar imagem/APK, nem criar commit, push, merge ou PR. Não declarar a Fase 34 validada no piloto.

## Entrega funcional

1. Defina contratos explícitos para filtros, período máximo, paginação/limites, ordem estável, fuso exibido, identificação mínima do funcionário, unidade/equipe autorizada e tratamento de períodos sem registros. Diferencie data civil de `data_operacional`; não crie ou modifique snapshots em consultas de relatório. Um snapshot ausente deve ser indicado como tal, sem jornada inventada.
2. Use a **mesma visão efetiva** para tela e todas as exportações. Correções aprovadas de instante, tipo e inclusão devem aparecer; rejeitadas/canceladas não. A marcação original continua imutável. Um espelho deve apresentar origem/ajuste de forma inteligível, sem expor biometria, anexos, fotos, embeddings, scores, coordenadas ou segredos.
3. Implemente espelho por funcionário e período, com marcações esperadas e efetivas quando houver snapshot, estados informativos de folga/sem jornada/incompleto, solicitações e correções pertinentes. Jornadas que atravessam meia-noite devem permanecer na data operacional de início. Não converter ausência de snapshot ou marcação em falta trabalhista presumida.
4. Implemente relatório consolidado de solicitações e ocorrências com filtros e contagens no escopo autorizado. Atrasos e dias sem marcação podem ser exibidos **somente como indicadores operacionais**, com regra e tolerância explicitadas. O plano registra tolerância inicial de cinco minutos (RN-011), mas sua adoção no relatório deve ser confirmada pelo RH; até lá, apresente o dado factual e marque a classificação como pendente. Não calcular horas extras, descontos, adicional noturno, banco de horas ou folha.
5. Acrescente XLSX mantendo CSV/PDF/DOCX existentes. Use uma biblioteca mantida e compatível com o runtime somente se necessário; valide a dependência no build. Proteja CSV/XLSX contra fórmula injetada por campos textuais, use MIME e nomes de arquivo seguros, limites de linhas/tamanho e geração proporcional à memória. Evite imprimir dados pessoais nos logs.
6. Aplique RBAC e isolamento tenant: funcionário apenas seu espelho se houver contrato pessoal; gestor apenas equipe/unidade autorizada; RH/admin apenas a empresa autenticada. Filtros do cliente nunca definem empresa. Fora do escopo e cross-tenant retornam 404 não enumerável. Teste IDOR, filtros inválidos e exportações em todos os formatos.
7. Atualize as interfaces de gestão e, se houver contrato pessoal, a interface do funcionário, preservando acessibilidade e mensagens claras. Não replique lógica autoritativa no cliente.

## Verificação e relatório

- Execute testes unitários e integração PostgreSQL/pgvector **descartável** com fixtures sintéticas: jornada diurna/noturna, timezone/DST, intervalo incompleto, folga, sem jornada, correção aprovada/rejeitada/cancelada, inclusão, concorrência, períodos vazios, isolamento tenant, escopo do gestor e equivalência tela/CSV/PDF/DOCX/XLSX. Verifique que consultas/exportações não alteram `marcacoes`, `correcoes` ou snapshots.
- Execute a descoberta backend, suítes de regressão pertinentes, `flutter analyze`/`flutter test` se o mobile for tocado e `git diff --check`. Registre apenas resultados realmente obtidos; skips opt-in não contam como aprovação de integração.
- Registre em `docs/FASE_34_RELATORIOS_ESPELHO_PONTO.md` contratos, decisões, matriz RF-046–RF-050, casos, resultados, limitações, dados exibidos, riscos de privacidade, pendências de RH/jurídico e o status separado de implementação local versus homologação externa. Se uma decisão de regra trabalhista ou acesso mudar materialmente o resultado, pare nesse ponto e peça a decisão do usuário.
