# Runbooks operacionais — anexos privados

Estes procedimentos não autorizam ações em produção. Qualquer comando destrutivo
deve ser aprovado, ter alvo explícito e ser precedido por snapshot e dry-run. Nunca
desabilite autorização, quarentena, ClamAV, retenção ou auditoria.

## 1. Backlog crescente

### Sintomas
`ApproximateAgeOfOldestMessage`, `OutboxBacklog` ou quarentena aumentam.
### Métricas
Fila visível/em voo, idade do job, heartbeat, duração p90/p99 e falhas.
### Diagnóstico
Confirmar dispatcher, worker, banco, fila, storage e scanner sem inspecionar payloads.
### Contenção
Pausar novos uploads somente se a capacidade segura estiver esgotada; downloads limpos continuam.
### Recuperação
Restaurar dependências e ampliar workers gradualmente; não executar consumidor no Gunicorn.
### Validação
Idade e profundidade caem, jobs concluem e anexos continuam bloqueados até `limpo`.
### Evidências
Preservar métricas, IDs opacos, timestamps, versão implantada e eventos sanitizados.

## 2. Mensagens na DLQ e redrive

### Sintomas
Alarme DLQ e crescimento de `ApproximateNumberOfMessagesVisible` na DLQ.
### Métricas
Recebimentos, falhas terminais, tentativas e idade da DLQ.
### Diagnóstico
Classificar versão inválida, dependência indisponível ou defeito usando IDs opacos.
### Contenção
Suspender redrive automático; mensagens não podem liberar anexos.
### Recuperação
Corrigir a causa e executar redrive controlado, com lote pequeno e política IAM de operador.
### Validação
DLQ esvazia, efeitos não duplicam e jobs terminais não reabrem.
### Evidências
Preservar contagens antes/depois, change ticket e auditoria; nunca copiar corpo da mensagem.

## 3. Scanner indisponível

### Sintomas
Readiness do worker falha, `ScannerAvailable=0` e jobs ficam reprocessáveis.
### Métricas
Disponibilidade, timeouts, falhas de scan e quarentena atrasada.
### Diagnóstico
Verificar rede local, processo clamd, recursos e `PING`, sem submeter conteúdo real.
### Contenção
Manter todos os anexos não limpos bloqueados e interromper consumo se necessário.
### Recuperação
Restaurar clamd, validar EICAR em ambiente descartável e retomar workers gradualmente.
### Validação
Readiness volta, assinatura está atual e jobs concluem sem liberação prematura.
### Evidências
Preservar versão, horários e códigos sanitizados; não guardar amostras do cliente.

## 4. Assinaturas ClamAV desatualizadas

### Sintomas
Alarme de idade, readiness falha ou resposta `VERSION` ausente/inválida.
### Métricas
`ClamAVSignatureAge`, última atualização válida e resultado do freshclam.
### Diagnóstico
Verificar logs operacionais do freshclam, DNS/egress e espaço do volume de assinaturas.
### Contenção
Parar scans; nunca aceitar resultado enquanto a idade exceder o limite.
### Recuperação
O operador atualiza via freshclam fora da aplicação e reinicia o scanner se necessário.
### Validação
Versão/data são parseáveis, idade está no limite e EICAR continua detectado.
### Evidências
Preservar versão, idade e resultado; não registrar comandos com credenciais.

## 5. Storage indisponível

### Sintomas
Readiness falha, leituras/promoções falham e o worker deixa mensagens sem confirmação.
### Métricas
Falhas de storage, latência, retries e objetos divergentes.
### Diagnóstico
Verificar endpoint/TLS, role, bucket privado e limites sem listar objetos na API pública.
### Contenção
Manter quarentena e suspender purga; não trocar para storage local em produção.
### Recuperação
Restaurar a configuração server-side e validar checksum em objeto sintético descartável.
### Validação
Read/write/delete sintético passa, backlog drena e nenhum objeto órfão é criado.
### Evidências
Preservar IDs de request sanitizados e horários; nunca URL, chave completa ou credencial.

## 6. Detecção de Malware

### Sintomas
Job conclui como infectado e download responde bloqueado sem bytes.
### Métricas
Resultados infectados e retenção curta, sem nomes ou dimensões por tenant.
### Diagnóstico
Confirmar código sanitizado do scanner e integridade do fluxo, sem renderizar/extrair o arquivo.
### Contenção
Manter objeto inacessível em quarentena e preservar retenção investigativa configurada.
### Recuperação
Não promover; seguir processo de incidente e purgar somente após elegibilidade do banco.
### Validação
Estado permanece `infectado`, download é 423 e trilha de auditoria está íntegra.
### Evidências
Preservar IDs opacos, hash apenas na trilha autorizada e resultado sanitizado.

## 7. Divergência de Reconciliação

### Sintomas
Metadado sem objeto, objeto órfão, checksum divergente ou quarentena sem job.
### Métricas
`ReconciliationDivergences` por tipo de baixa cardinalidade e contagens do dry-run.
### Diagnóstico
Executar `reconcile_correction_attachments.py` sem `--execute`, tenant-scoped quando aplicável.
### Contenção
Bloquear download do registro divergente; nunca apagar objeto desconhecido automaticamente.
### Recuperação
Usar somente reparo explícito suportado, lote limitado e auditoria; escalar demais casos.
### Validação
Novo dry-run não encontra a divergência e as constraints continuam válidas.
### Evidências
Preservar relatório sanitizado, IDs opacos, cursor de retomada e autorização da mudança.

## 8. Continuidade e restauração descartável

### Sintomas
Exercício programado ou necessidade de validar metadados após incidente.
### Métricas
Contagem exportada/restaurada, checksums válidos, jobs retomáveis e divergências.
### Diagnóstico
Confirmar que origem e destino são bancos/storage descartáveis isolados.
### Contenção
Proibir uso de backup real ou endpoint externo durante o exercício.
### Recuperação
Restaurar metadados em nova base, copiar objetos sintéticos e retomar outbox pendente.
### Validação
Limpos permanecem íntegros; quarentena/infectados permanecem sem download.
### Evidências
Preservar comandos, versões e contagens, depois comprovar remoção dos temporários.

## 9. Rollback de configuração seguro

### Sintomas
Nova configuração de fila, scanner ou storage causa readiness indisponível.
### Métricas
Readiness, heartbeat, backlog, DLQ e falhas por dependência.
### Diagnóstico
Comparar somente configuração server-side versionada e valores não secretos.
### Contenção
Parar dispatcher/worker afetado; não selecionar fila falsa ou scanner bypass.
### Recuperação
Reverter para a última configuração válida mantendo modo assíncrono e fail-closed.
### Validação
Dependências prontas, assinaturas atuais, backlog retomado e downloads seguem no gate.
### Evidências
Preservar diff, horários, aprovação e resultados de smoke tests sanitizados.
