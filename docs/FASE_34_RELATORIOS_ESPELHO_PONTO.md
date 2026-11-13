# Fase 34 — relatórios e espelho de ponto

Data da validação local: **21/10/2026**.

Esta entrega é local e usa somente dados sintéticos. Não houve acesso a AWS,
Supabase remoto, produção ou banco do piloto. Não houve publicação, commit,
push, merge ou PR. A implementação não calcula folha, banco de horas, falta,
hora extra, desconto ou adicional e não constitui homologação trabalhista.

## Estado da entrega

| Dimensão | Estado | Limite |
|---|---|---|
| Implementado localmente | concluído para RF-046–RF-050 no escopo abaixo | código, unidades e PostgreSQL/pgvector TLS descartável |
| Regra trabalhista validada | **não** | depende de RH/jurídico; RN-011 permanece pendente |
| Validado no piloto | **não** | a Fase 32 continua parcialmente homologada |

A EC2 não foi consultada. Este relatório não reconfirma estado remoto e apenas
preserva o último estado `stopped` documentado na Fase 32.

## Referência e preservação do checkout

- branch: `codex/aws-pilot-testing`;
- HEAD de origem: `e1cd6fed1232c0e32f62920d938cd1ae18da5d95`;
- fingerprint SHA-256 do manifesto ordenado dos nove arquivos de
  implementação/teste:
  `be4b181f92944987096c40e02f1d91ca2bf9433dc9f28f23e899551f7e734cc0`;
- alterações preexistentes das Fases 32 e 33, relatórios, imagens de marca,
  `document-assets/`, `output/` e `tmp/` foram preservadas;
- migrations continuam `001`–`026`; nenhuma migration foi necessária;
- nenhuma foto, vetor biométrico, localização, anexo, dump ou segredo foi
  criado ou incluído.

## Fonte autoritativa

O espelho combina duas fontes sem escrever no banco:

1. `services/effective_timekeeping.py`: marcações confirmadas, correções de
   instante/tipo aprovadas e inclusões aprovadas; correções rejeitadas ou
   canceladas nunca alteram o resultado;
2. `jornadas_diarias` e `jornada_eventos_esperados`: snapshot imutável,
   `data_operacional`, timezone e eventos esperados.

As conexões de relatório são abertas como transações PostgreSQL `read only` e
terminam com rollback defensivo. O serviço de relatório não contém `INSERT`,
`UPDATE`, `DELETE` nem chamada de materialização de snapshot. A integração
comparou contagens e digest das marcações antes/depois da consulta.

## Data operacional e jornadas noturnas

Marcações já ligadas a `jornada_evento_id` herdam diretamente a
`data_operacional` do snapshot. Assim, uma jornada sintética das 22h de
20/10/2026 às 06h de 21/10/2026 aparece integralmente em **20/10/2026**.

Uma inclusão aprovada sem marcação original é associada somente para
apresentação ao evento esperado de mesmo tipo mais próximo, dentro de janela de
±12 horas. Solicitações sem marcação original usam o snapshot temporalmente
mais próximo na mesma janela. Isso não modifica vínculo, snapshot ou marcação.
Ambiguidade entre snapshots sobrepostos permanece risco residual e exige
revisão operacional; a apresentação nunca escolhe escala inexistente.

Sem snapshot, o dia é `sem_evidencia` ou `snapshot_ausente`, e não “falta”. O
fuso é explícito por snapshot. Limites UTC usam `zoneinfo`; o teste de transição
DST comprovou uma janela de 47 horas com margens em um dia civil de 23 horas,
sem presumir duração fixa. Instantes esperados já materializados continuam
`timestamptz`, evitando resolver novamente horários ambíguos.

## Contratos implementados

### Espelho de gestão

`GET /api/gestao/espelho`

- papéis: `administrador`, `rh` e `gestor`;
- parâmetros obrigatórios: `funcionario_id`, `inicio`, `fim`;
- período máximo inclusivo: 366 dias;
- tenant sempre vem da sessão; `empresa_id` do cliente é recusado;
- gestor usa `gestores_escopos` por unidade/equipe;
- fora do tenant/escopo ou inexistente: 404 não enumerável;
- ordem: `data_operacional`, eventos por `ordem` e ID;
- resposta: identificação mínima, período, fuso, dias, eventos esperados e
  efetivos, origem do ajuste, solicitações sem motivo/anexo e resumo factual.

Estados informativos: `completo`, `incompleto`, `sem_marcacao`, `folga`,
`folga_com_marcacao`, `sem_jornada`, `sem_jornada_com_marcacao`,
`snapshot_ausente` e `sem_evidencia`.

### Espelho pessoal

`GET /api/me/espelho`

- papel: `funcionario`;
- usa exclusivamente empresa e funcionário da sessão;
- recusa `funcionario_id` ou `empresa_id` informados pelo cliente;
- mesmo período máximo e mesma visão do espelho de gestão.

### Exportação do espelho

`GET /api/gestao/espelho/exportar`

- mesmos filtros, escopo e período do espelho;
- `formato`: `csv`, `pdf`, `xlsx`, `word`, `doc` ou `docx`;
- CSV, PDF, DOCX e XLSX recebem as mesmas linhas ordenadas da tela;
- nomes fixos e sem PII: `espelho_ponto.<extensão>`;
- `Content-Disposition: attachment`, MIME específico, `nosniff` e
  `Cache-Control: private, no-store`;
- CSV/XLSX neutralizam texto iniciado por `=`, `+`, `-` ou `@`;
- XLSX é gerado em modo write-only por `openpyxl 3.1.5`.

O endpoint legado `GET /exportar-pontos` e seus CSV/PDF/DOCX foram preservados;
XLSX foi acrescentado sem remover formatos ou aliases. Ele também passou a
respeitar a data operacional quando há snapshot e mantém limite de 10.000
linhas. A dependência foi fixada em `requirements.txt`; `pip check` passou.

### Consolidado

`GET /api/gestao/relatorios/consolidado`

- papéis: `administrador`, `rh` e `gestor`;
- período obrigatório, máximo de 92 dias;
- filtros opcionais: funcionário, unidade e equipe, sempre subordinados ao
  tenant e escopo da sessão;
- `pagina` positiva, `limite` de 1 a 100, `tem_mais` e ordem estável por nome/ID;
- por funcionário: unidade/equipe, snapshots, lacunas de evidência, jornadas
  incompletas, dias com jornada e nenhuma marcação, eventos posteriores ao
  horário, solicitações por estado/categoria e ocorrências por tipo/estado.

Os indicadores são factuais. `eventos_apos_horario` significa somente diferença
positiva entre instantes. `dias_com_jornada_sem_marcacao` exige snapshot com
eventos esperados. Nenhum deles decide falta, atraso trabalhista ou efeito em
folha.

## Matriz RF-046–RF-050

| Requisito | Implementação local | Evidência/limite |
|---|---|---|
| RF-046 — marcações por funcionário | `/api/gestao/pontos` preservado e espelho por período | mesma visão efetiva; data operacional corrigida |
| RF-047 — atrasos, ausências e solicitações | consolidado factual, estados/categorias e ocorrências | cinco minutos e classificação trabalhista pendentes |
| RF-048 — espelho de ponto | gestão e pessoal, esperado/efetivo/ajustes/estados | não materializa snapshot; lacuna é explícita |
| RF-049 — PDF, Excel, CSV e Word | CSV/PDF/DOCX/XLSX no espelho e XLSX no legado | equivalência de linhas testada; fórmula neutralizada |
| RF-050 — geração pelo RH | RH/admin no tenant; gestor em escopo autorizado | sem acesso cross-tenant; 404 não enumerável |

## Dados exibidos e privacidade

Incluídos somente quando necessários: nome, matrícula, unidade/equipe, data
operacional, fuso, tipo, horário esperado/efetivo, diferença em minutos, origem
`original`/`correcao_aprovada`/`inclusao_aprovada`, duração descritiva e estados
agregados de solicitações/ocorrências.

Excluídos: fotos, embeddings, scores, tentativas faciais individualizadas,
anexos, motivos livres, decisões livres, coordenadas, endereços, chaves privadas,
segredos e dados de outro tenant. As rotas não registram linhas exportadas em
log e os nomes dos arquivos não contêm PII.

## Testes executados

| Validação | Resultado em 21/10/2026 |
|---|---|
| baseline `test_timekeeping_management.py` antes da mudança | 21/21 |
| regressões de gestão/exportações após a mudança | 21/21 |
| regressões unitárias/rotas Fase 34 | 14/14 |
| integração Fase 34 em PostgreSQL 16/pgvector com TLS | 3/3 |
| descoberta backend `test_*.py` | 376 testes: 274 sucessos, 102 skips opt-in, 0 falhas |
| compilação dos Python alterados | passou |
| `node --check static/js/controleponto.js` | passou |
| `python -m pip check` | nenhuma dependência quebrada |
| `git diff --check` | passou; somente avisos de normalização LF/CRLF |

A integração aplicou migrations `001`–`026`, usou certificado TLS sintético de
um dia e dados artificiais. Cobriu jornada 22h–06h, correção aprovada, inclusão
rejeitada, associação de solicitações, tenant, consolidado real e digest
imutável. O contêiner
`frequenia-phase34-postgres` foi removido ao final. Os 102 skips da descoberta
são integrações opt-in; a integração específica da Fase 34 foi executada
separadamente e não ficou como skip.

Flutter não foi alterado; portanto `flutter analyze` e `flutter test` não foram
repetidos nesta fase. CI remota não foi verificada porque não houve commit ou
push autorizado.

## Decisões pendentes de RH/jurídico

| Decisão | Estado técnico atual |
|---|---|
| adotar ou não os cinco minutos de RN-011 | pendente; interface não classifica tolerância/atraso |
| significado de marcação posterior ao esperado | apenas diferença factual |
| significado de dia com snapshot e nenhuma marcação | apenas indicador operacional |
| tratamento de folga com marcação ou jornada incompleta | estado informativo, sem efeito automático |
| cálculo de duração para folha | não implementado; duração é descritiva |
| horas extras, adicionais, descontos e banco de horas | fora de escopo |
| prazo e finalidade dos relatórios/exportações | pendente de política organizacional |
| acesso pessoal e forma de disponibilização externa | contrato API local existe; experiência final depende de homologação |

## Riscos residuais e critérios externos

- inclusões sem vínculo direto podem ser temporalmente ambíguas se snapshots se
  sobrepuserem; devem ser revisadas, não remapeadas automaticamente;
- o consolidado faz consultas por funcionário, adequado ao piloto, mas deve ter
  carga/latência observada antes de ampliar escala;
- navegadores, leitores de PDF/DOCX/XLSX e acessibilidade da tabela precisam de
  homologação nos dispositivos representativos;
- regras e rótulos trabalhistas dependem de aprovação formal;
- antes de validar no piloto, a barreira de banco/TLS/backup/restore da Fase 32
  precisa ser superada e versão/digest executados precisam ser comprovados;
- futura homologação deve repetir IDOR, gestor multiunidade, tenant, períodos
  vazios/limite, noturno/DST, correções, folga, sem jornada, exportações e prova
  de ausência de escrita com dados formalmente autorizados.

## Conclusão

A Fase 34 está **implementada e validada localmente** para o escopo descrito.
Não está validada no piloto e nenhuma regra trabalhista foi aprovada. A Fase 32
permanece **parcialmente homologada**; as pendências jurídicas da Fase 33 não
foram alteradas.

Em 24/10/2026, os testes locais focados passaram (17 executados, 3 integrações
opt-in ignoradas). A restauração local do schema `public` do backup do piloto
passou, mas o restore integral dos schemas internos do Supabase não concluiu;
não houve validação autenticada da Fase 34 na AWS nem mudança no banco ativo.
