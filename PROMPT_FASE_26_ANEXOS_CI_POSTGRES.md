# Prompt — FrequenIA — Fase 26: Anexos seguros de correções e CI PostgreSQL

Trabalhe no repositório FrequenIA e implemente a Fase 26 preservando integralmente as garantias homologadas nas Fases 24 e 25.

## Missão

Entregar dois resultados:

1. suporte seguro a um comprovante opcional em solicitações de correção;
2. automação da suíte homologada em CI com PostgreSQL e pgvector descartáveis.

O anexo deve ser privado, autorizado pelo backend e vinculado à solicitação sem alterar a marcação original. A CI deve provar migrations, workflow, concorrência e testes unitários sem depender de Supabase, credenciais reais ou serviços externos.

## Contexto confirmado

Já existem:

- workflow Gestor → RH homologado;
- migration `018_correction_manager_hr_workflow.sql`;
- testes PostgreSQL em `tests/test_phase25_postgres_integration.py`;
- matriz de aceite em `docs/FASE_25_HOMOLOGACAO.md`;
- autenticação, RBAC, isolamento por empresa e escopo do gestor;
- solicitações de correção no web e no Flutter;
- visão efetiva e exportações que preservam `marcacoes`;
- auditoria append-only;
- CI atual de secret scanning.

Antes de editar, leia o relatório da Fase 25 e inspecione o estado do Git. O `AGENTS.md` local pode ainda descrever a Fase 25; use-o para preservar as garantias já homologadas, mas considere este prompt a instrução mais recente quanto ao novo escopo de anexos e CI. Preserve todas as mudanças preexistentes do usuário.

## Parte A — Anexos seguros

### Modelo mínimo do piloto

- Cada solicitação pode possuir no máximo um comprovante opcional.
- Formatos aceitos: PDF, JPEG e PNG.
- Tamanho máximo: 10 MiB.
- O arquivo pode ser enviado na criação ou enquanto a solicitação estiver `pendente_gestor` e pertencer ao solicitante.
- Depois que a solicitação sair de `pendente_gestor`, o funcionário não pode incluir, substituir ou remover o comprovante.
- Gestor autorizado, RH/admin da empresa e o próprio solicitante podem consultar os metadados e baixar o arquivo.
- Funcionário diferente, gestor fora do escopo e usuário de outra empresa recebem a mesma resposta não enumerável usada pelo restante do sistema.
- Não criar URL pública permanente.
- Não armazenar conteúdo binário diretamente na tabela `correcoes`.

### Banco

Criar migration incremental posterior à última migration existente, sem renumerar arquivos.

Criar tabela `anexos_correcao` com, no mínimo:

- `id` UUID;
- `empresa_id`;
- `correcao_id`;
- `funcionario_id`;
- `enviado_por_usuario_id`;
- chave privada do objeto;
- nome original normalizado;
- tipo MIME verificado;
- tamanho em bytes;
- SHA-256;
- estado do arquivo;
- timestamps produzidos pelo banco.

Requisitos:

- chaves estrangeiras e tenant compostos quando compatíveis com o schema;
- unicidade que limite um anexo por correção;
- constraints de tamanho, MIME e estados;
- índice para consulta por empresa e correção;
- nenhuma cascata que apague silenciosamente histórico auditável;
- migration validada tanto em instalação limpa quanto em upgrade `001` até a migration anterior.

### Armazenamento

Criar uma interface de armazenamento privado desacoplada das rotas.

- Usar chaves geradas pelo servidor com UUID; nunca usar o nome fornecido como caminho.
- Impedir path traversal e caminhos absolutos.
- Não registrar conteúdo, URL assinada, token ou chave de armazenamento em logs.
- Para testes, usar diretório temporário descartável fora do repositório.
- Não escolher ou provisionar serviço de produção nesta fase.
- O backend deve falhar de forma segura quando o armazenamento não estiver configurado.
- Gravação do objeto e persistência do metadado precisam de compensação: falha no banco remove o objeto recém-gravado; falha na remoção não pode apagar o histórico silenciosamente.

### Validação de arquivo

- Validar extensão, MIME declarado e assinatura real do arquivo.
- Rejeitar discrepância entre extensão, MIME e conteúdo.
- Rejeitar arquivo vazio, truncado ou acima do limite antes de persistir metadados.
- Normalizar o nome exibido, removendo controles e limitando o tamanho.
- Não executar, renderizar no servidor nem extrair conteúdo do arquivo.
- Responder downloads com `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` e tipo validado.
- Registrar como limitação que varredura antimalware dedicada continua necessária antes de produção, caso nenhum mecanismo já exista no projeto.

### API e domínio

Preferir endpoints explícitos e regras centralizadas em serviço:

- enviar/substituir comprovante da própria solicitação pendente;
- consultar metadados autorizados;
- baixar conteúdo autorizado;
- remover o próprio comprovante somente em `pendente_gestor`, preservando auditoria.

Se for necessário alterar a criação da solicitação, manter compatibilidade com o JSON atual. Não aceitar campos de autoridade do cliente.

Toda inclusão, substituição, download administrativo e remoção deve gerar auditoria sanitizada contendo IDs, papel, tamanho, MIME e SHA-256, sem conteúdo ou caminho físico.

### Interfaces

Web pessoal e Flutter devem permitir:

- escolher comprovante opcional;
- mostrar nome, tipo, tamanho e estado;
- explicar formatos e limite;
- informar falhas de validação em linguagem simples;
- permitir remoção/substituição somente quando o backend autorizar.

Interface administrativa deve:

- indicar existência do comprovante;
- permitir download somente quando autorizado;
- não incorporar automaticamente PDF ou imagem na página;
- continuar mostrando estados, ações e timeline da correção.

Backend permanece a autoridade para todas as ações.

## Parte B — CI com PostgreSQL e pgvector

Criar ou atualizar workflow GitHub Actions para pull requests e pushes relevantes.

O job deve:

1. subir PostgreSQL compatível com pgvector;
2. aguardar health check;
3. instalar dependências Python de forma reproduzível;
4. aplicar migrations em banco limpo;
5. executar testes unitários `test_*.py`;
6. executar `tests/test_phase25_postgres_integration.py` com opt-in explícito;
7. executar os novos testes PostgreSQL de anexos;
8. executar `flutter analyze` e `flutter test` em job separado;
9. não usar `.env` local nem secrets de produção;
10. sempre destruir serviços e arquivos temporários ao final.

Use somente credenciais descartáveis definidas no próprio workflow. Não exponha portas além do necessário ao runner. Fixe versões principais das actions e documente a política de atualização.

Mantenha o secret scanning existente.

## Testes obrigatórios

### Anexos

1. solicitação sem anexo continua válida;
2. PDF válido é aceito;
3. JPEG válido é aceito;
4. PNG válido é aceito;
5. arquivo vazio é rejeitado;
6. tamanho acima de 10 MiB é rejeitado;
7. extensão não permitida é rejeitada;
8. MIME não permitido é rejeitado;
9. assinatura divergente é rejeitada;
10. nome malicioso não controla o caminho;
11. path traversal é inerte;
12. solicitante envia em `pendente_gestor`;
13. solicitante substitui em `pendente_gestor`;
14. solicitante remove em `pendente_gestor`;
15. estado encaminhado/final bloqueia mutação;
16. outro funcionário não lê nem baixa;
17. gestor no escopo baixa;
18. gestor fora do escopo recebe 404 não enumerável;
19. RH/admin da própria empresa baixam;
20. cross-tenant não enumera existência;
21. download usa headers seguros;
22. metadado não contém caminho físico ou segredo;
23. auditoria é criada nas ações previstas;
24. falha no banco compensa objeto novo;
25. falha no armazenamento não cria metadado órfão;
26. duas inclusões concorrentes respeitam o limite de um anexo;
27. workflow Gestor → RH continua passando;
28. marcação original permanece inalterada;
29. visão efetiva e exportações não mudam por causa do anexo;
30. ocorrências `falha_facial` não sofrem regressão.

### CI

- validar sintaxe e conteúdo do workflow por teste automatizado;
- comprovar que nenhum segredo real é necessário;
- comprovar que a suíte PostgreSQL não é silenciosamente ignorada no CI;
- manter execução local documentada equivalente à execução do CI.

## Restrições

- Não acessar ou alterar produção.
- Não executar deploy.
- Não realizar commit, push, merge ou abrir PR sem pedido explícito.
- Não apagar, restaurar ou sobrescrever mudanças preexistentes do usuário.
- Não criar bucket, conta cloud ou credencial externa.
- Não adicionar URL pública de arquivo.
- Não armazenar anexos em Git, no banco como bytea/base64 ou em diretório público do Flask.
- Não alterar estados ou transições homologados nas Fases 24 e 25.
- Não alterar a marcação original.
- Não implementar push, XLSX, espelho de ponto, escalas avançadas, backup/restauração ou LGPD completa.
- Não ampliar o cadastro biométrico ou modificar os modelos faciais.

## Validação final

Executar e registrar:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Executar a suíte PostgreSQL completa pelo comando documentado, incluindo Fases 25 e 26.

Em `mobile/`:

```powershell
flutter analyze
flutter test
```

Validar também o workflow de CI sem usar segredos reais. Se a execução remota não estiver autorizada ou disponível, validar localmente a configuração e informar explicitamente que o run remoto permanece pendente.

## Documentação e entrega

Atualizar:

- `README.md`;
- documentação de configuração local;
- matriz de migrations;
- comandos de testes unitários, PostgreSQL e Flutter;
- política do anexo no piloto;
- limitações de armazenamento e antimalware;
- checklist de homologação.

Entregar relatório `docs/FASE_26_ANEXOS_CI.md` contendo:

1. decisão formal do modelo de anexo;
2. migration criada;
3. serviço e endpoints;
4. autorização por papel;
5. validações e headers de segurança;
6. auditoria;
7. interfaces web e Flutter;
8. CI PostgreSQL/pgvector;
9. testes executados e resultados exatos;
10. limitações;
11. itens recomendados para a Fase 27.

Não declarar a Fase 26 concluída enquanto houver falha de teste, arquivo público, possibilidade de path traversal, autorização apenas no frontend, objeto/metadado órfão conhecido, suíte PostgreSQL ignorada no CI ou Flutter não validado.
