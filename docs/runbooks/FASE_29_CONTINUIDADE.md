# Runbooks de continuidade da Fase 29

Regras comuns: usar apenas ambiente isolado e dados sintéticos; exigir papel
autorizado; iniciar com dry-run; preservar IDs opacos, timestamps, manifestos e
checksums; nunca registrar segredo, PII, chave completa ou conteúdo; nunca
desabilitar scanner, autorização, retenção ou auditoria.

## 1. Backup atrasado ou inválido
Sinais: idade/alarme ou integridade falha. Impacto: recuperação incerta.
Pré-condições/papéis: operador aprovado e destino isolado. Triagem: verificar
último manifesto e dependências. Contenção: não substituir conjunto íntegro.
Execução: corrigir causa e criar novo conjunto. Validação: manifesto e hashes.
Rollback: remover somente conjunto novo inválido. Evidência: IDs/contagens.
Proibição: declarar conjunto parcial restaurável.

## 2. Restauração interrompida
Sinais: journal sem marcador final. Impacto: destino inconsistente.
Pré-condições/papéis: operador de restore. Triagem: validar origem novamente.
Contenção: isolar destino. Execução: retomar pelo journal ou recriar destino.
Validação: checksums e estados de download. Rollback: excluir apenas destino
descartável confirmado. Evidência: journal sanitizado. Proibição: promover antes
da verificação final.

## 3. RPO/RTO acima do objetivo
Sinais: métricas observadas acima do parâmetro. Impacto: objetivo não atendido.
Pré-condições/papéis: responsável de continuidade. Triagem: separar espera,
transferência e validação. Contenção: registrar desvio sem mudar SLO. Execução:
ajustar capacidade em homologação. Validação: novo exercício. Rollback: voltar
configuração anterior. Evidência: percentis e versão. Proibição: converter uma
execução local em compromisso de produção.

## 4. Redrive seguro da DLQ
Sinais: DLQ > 0. Impacto: anexos em quarentena. Pré-condições/papéis: operador
de redrive, motivo e lote. Triagem: plano e validação de payload/tenant.
Contenção: preservar origem. Execução: lote pequeno e abortar na taxa de falha.
Validação: jobs terminais não reabriram e backlog drenou. Rollback: parar novas
movimentações; não apagar evidência. Proibição: editar resultado do scanner.

## 5. Corrupção ou divergência de objeto
Sinais: tamanho/checksum divergente. Impacto: download bloqueado. Pré-condições:
reconciliação dry-run. Papéis: operador de storage. Triagem: comparar manifesto,
banco e objeto. Contenção: manter fail-closed. Execução: restaurar somente cópia
verificada. Validação: checksum e autorização. Rollback: voltar ao objeto
preservado. Evidência: IDs opacos/hash autorizado. Proibição: renderizar arquivo.

## 6. Indisponibilidade prolongada
Sinais: readiness, heartbeat e falhas de banco/fila/storage/scanner. Impacto:
backlog. Pré-condições: dependência identificada. Papéis: operação e segurança.
Triagem: testar uma dependência por vez. Contenção: uploads podem ser suspensos,
downloads limpos permanecem autorizados. Execução: restaurar serviço e drenar
gradualmente. Validação: readiness/assinaturas/backlog. Rollback: configuração
anterior segura. Evidência: métricas. Proibição: fallback local em produção.

## 7. Esgotamento de capacidade/backlog
Sinais: idade, profundidade e p99 crescentes. Impacto: RTO degradado.
Pré-condições: carga sintética limitada. Papéis: operação. Triagem: publisher,
worker e scanner. Contenção: limitar entrada. Execução: ajustar workers em
homologação. Validação: drenagem e taxa de erro. Rollback: capacidade anterior.
Evidência: percentis. Proibição: carga ilimitada ou endpoint público.

## 8. Tag purge-eligible incorreta ou atrasada
Sinais: divergência de tagging. Impacto: risco de retenção. Pré-condições:
registro, retenção e autorização persistidos. Papéis: operador de retenção.
Triagem: dry-run e checksum. Contenção: adicionar hold e suspender lifecycle.
Execução: reprocessar job válido; tag incorreta exige mudança aprovada.
Validação: ativo/quarentena sem tag. Rollback: remover tag somente por processo
auditado. Evidência: job/contagens. Proibição: aceitar chave arbitrária.

## 9. Rollback do exercício e preservação
Sinais: falha do exercício. Impacto: evidência incompleta. Pré-condições: alvos
criados pelo próprio teste. Papéis: executor. Triagem: inventariar recursos.
Contenção: parar mutações. Execução: preservar manifesto/log sanitizado e
remover alvos exatos no finally. Validação: nenhum temporário ou serviço ativo.
Rollback: não se aplica a produção. Evidência: lista de limpeza. Proibição:
remoção ampla, glob ou alvo não resolvido.

## 10. Aprovação e revisão periódica
Sinais: política vencida ou pendente. Impacto: objetivos não oficiais.
Pré-condições: responsáveis de negócio, jurídico, segurança e operação. Papéis:
aprovadores formais. Triagem: revisar classificação, custos e exercícios.
Contenção: manter status pendente. Execução: registrar decisão/referência sem
segredo. Validação: configuração e runbooks revisados. Rollback: revogar flag e
manter fail-closed. Evidência: ID da decisão. Proibição: inventar aprovação.
