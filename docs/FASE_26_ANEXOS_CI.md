# Fase 26 — Anexos privados e CI PostgreSQL/pgvector

Data da validação local: 8 de outubro de 2026.

## Decisão formal do modelo

Cada correção possui no máximo um comprovante **ativo**, mas versões
substituídas/removidas permanecem como metadados históricos append-only em
`anexos_correcao`. O objeto usa chave aleatória UUID gerada pelo servidor e
fica num armazenamento privado desacoplado, nunca em `correcoes`, `bytea`,
base64, Git ou `static/`. Remoção pelo usuário é lógica; uma política posterior
de retenção/purga poderá eliminar objetos históricos com trilha operacional.

A solicitação sem comprovante não muda. O comprovante pode ser incluído na
criação multipart ou enviado/substituído/removido pelo solicitante enquanto a
correção estiver `pendente_gestor`. A autoridade permanece no backend.

## Migration 021

`supabase/migrations/021_correction_private_attachments.sql` cria a tabela com
IDs de empresa/correção/funcionário/remetente, chave opaca, nome normalizado,
MIME verificado, bytes, SHA-256, estado e timestamps do PostgreSQL. Possui:

- FKs compostas para tenant/funcionário/correção, todas sem cascade;
- checks de chave, nome, MIME, tamanho, SHA-256, estado e remoção;
- unicidade parcial de um anexo ativo por empresa/correção;
- índice de consulta por empresa, correção, estado e data.

A integração aplica `001`–`020`, insere correção representativa, aplica `021`
e comprova preservação; depois valida instalação limpa `001`–`021`.

## Serviço, endpoints e autorização

- `services/correction_attachment_storage.py`: armazenamento privado local do
  piloto, raiz explícita, chaves UUID e contenção de caminho;
- `services/correction_attachments.py`: validação, regras de domínio,
  transações, locks, auditoria, compensação e autorização;
- pessoais: `POST|PUT|GET|DELETE /api/ocorrencias/<id>/comprovante` e
  `GET .../download`;
- gestão: `GET /api/gestao/ocorrencias/<id>/comprovante` e `GET .../download`.

O solicitante vê apenas o próprio recurso. Gestor depende de unidade/equipe;
RH e administrador dependem da empresa autenticada. Funcionário distinto,
gestor fora do escopo e outro tenant recebem `404` não enumerável.

## Validação e resposta segura

Extensão, MIME declarado e assinatura real precisam concordar para PDF, JPEG
ou PNG. Arquivos vazios, truncados ou maiores que 10 MiB são rejeitados antes
do metadado. O nome passa por normalização Unicode, remoção de caminho e
controles e limite de 200 caracteres; ele nunca compõe a chave.

Downloads usam `Content-Disposition: attachment`,
`X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store` e o MIME
validado. Web administrativo oferece apenas link; não incorpora PDF/imagem.

## Auditoria e consistência

Inclusão, substituição, download de gestão e remoção geram eventos sanitizados
com IDs, papel, empresa, funcionário, tamanho, MIME, SHA-256 e estado. Conteúdo,
caminho físico, token e URL não entram na auditoria. Falha de persistência
compensa o objeto novo; falha de armazenamento não cria metadado. Duas
inclusões reais são serializadas pelo lock da correção e deixam exatamente um
registro ativo.

## Interfaces

As telas web pessoais aceitam comprovante na criação e permitem consultar,
baixar, substituir e remover quando pendente. A tela administrativa indica os
metadados e baixa pelo endpoint autorizado. O Flutter oferece seleção,
metadados e alteração/remoção quando pendente, preservando a navegação e os
cinco rótulos homologados.

## CI

`.github/workflows/phase26-quality.yml` mantém o secret scanning existente e
adiciona:

- job backend com `pgvector/pgvector:pg16`, health check e credenciais
  descartáveis no próprio workflow;
- dependências fixadas em `requirements-ci.txt`;
- migration limpa explícita, descoberta padrão, Fase 25 e Fase 26 opt-in;
- job Flutter separado com `flutter analyze` e `flutter test`;
- remoção incondicional do diretório temporário.

Actions são fixadas por major. Mudanças de major exigem revisão manual e nova
execução integral. O workflow não lê `.env`, Supabase ou secrets de produção.

## Matriz dos 30 cenários

| # | Evidência automatizada |
|---:|---|
| 1 | `test_01_request_without_attachment_remains_valid` |
| 2–4 | `test_02_pdf_jpeg_and_png_are_accepted` e `test_02b_attachment_can_be_sent_atomically_during_creation` |
| 5–9 | `test_03_invalid_empty_oversized_extension_mime_signature_and_truncation` |
| 10–11 | `test_04_name_and_path_are_inert_and_metadata_has_no_storage_secret` |
| 12–14 | `test_05_owner_can_upload_replace_and_remove_only_while_pending` |
| 15 | `test_06_forwarded_and_final_states_block_attachment_mutation` |
| 16 | `test_07_employee_authorization_is_non_enumerable` |
| 17–20 | `test_08_manager_scope_hr_admin_and_cross_tenant_authorization` |
| 21 | `test_09_download_has_safe_headers_and_does_not_inline_render` |
| 22 | `test_04_name_and_path_are_inert_and_metadata_has_no_storage_secret` |
| 23 | `test_10_attachment_actions_have_sanitized_audit` |
| 24 | `test_11_database_failure_compensates_new_object` |
| 25 | `test_12_storage_failure_does_not_create_orphan_metadata` |
| 26 | `test_13_two_real_concurrent_uploads_leave_one_active_attachment` |
| 27–29 | `test_14_workflow_marking_effective_view_and_export_ignore_attachment` + suíte Fase 25 |
| 30 | `test_15_facial_failure_workflow_remains_independent` |

## Resultados executados

Execução local final:

- migration limpa pelo comando da CI: 21 migrations aplicadas (`001`–`021`);
- descoberta backend: 237 testes, 189 aprovados, 48 skips explícitos de
  integração, 0 falhas e 0 erros;
- integração PostgreSQL Fase 25: 31 aprovados, 0 falhas, 0 skips;
- integração PostgreSQL Fase 26: 17 aprovados, 0 falhas, 0 skips;
- `flutter analyze`: sem issues;
- `flutter test`: 48 aprovados, 0 falhas;
- workflow CI: YAML parseado e quatro testes de contrato aprovados; run remoto
  pendente porque não houve commit, push ou execução remota autorizada.

No host Windows, `flutter pub get` resolveu e registrou `file_picker`, mas o SDK
também informou que builds desktop com plugins exigem suporte a symlink/Modo do
Desenvolvedor. Nenhuma configuração global da máquina foi alterada; isso não
impediu `flutter analyze` nem os 48 testes.

## Limitações e Fase 27

- escolher/provisionar armazenamento privado durável de produção;
- integrar varredura antimalware, quarentena e métricas operacionais;
- formalizar retenção/purga dos objetos substituídos/removidos;
- observar o primeiro run remoto da CI e definir proteção de branch;
- habilitar suporte a symlink no host Windows somente se um build desktop for
  necessário e houver autorização para alterar essa configuração da máquina;
- avaliar download no Flutter via mecanismo nativo seguro, sem URL pública;
- manter fora de escopo push, XLSX, espelho, escalas avançadas, backup e LGPD
  operacional completa.
