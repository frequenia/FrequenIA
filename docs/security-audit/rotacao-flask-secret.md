# Rotação operacional do segredo Flask

O relatório de 17/09/2026 confirma que um segredo Flask antigo foi incluído no histórico Git. O código atual exige `FLASK_SECRET_KEY` em runtime; o valor histórico não deve ser recuperado, reutilizado nem copiado para documentação ou logs. A remediação de código não rotaciona credenciais de ambientes externos.

## Inventário antes da operação

- Local: `.env` ignorado pelo Git é carregado no início de `app.py` por `load_dotenv()`. `.env.example` contém apenas um placeholder, não uma chave utilizável. O Dockerfile não define nem copia a chave; `.dockerignore` exclui `.env*`. Um contêiner novo deve receber a variável no runtime, por exemplo via `--env-file .env` no ambiente local.
- `APP_ENV` aceita `development`, `homologation` e `production`; a validação de `FLASK_SECRET_KEY` é a mesma nos três: obrigatória, não pode ser o placeholder conhecido, deve ter ao menos 32 bytes e deve diferir de `JWT_SECRET_KEY`. Não há fallback de chave antiga nem `SECRET_KEY_FALLBACKS` configurado.
- Homologação e produção: identificar, com os responsáveis de cada implantação, o gerenciador de segredos, todos os contêineres/instâncias e eventuais jobs que importem `app.py`. Este repositório não contém manifestos de implantação desses ambientes; a presença ou o valor da chave neles não pode ser inferido do `.env` local.
- Confirmar se a chave foi reutilizada em outros serviços sem registrar valores em tickets ou logs. Tratar esses serviços no mesmo plano de resposta.
- Antes de revogar `auth_sessions`, confirmar o project ref Supabase e o banco **efetivamente usados** em cada ambiente, além de qualquer compartilhamento entre local, homologação e produção. `APP_ENV=development` não comprova exclusividade do banco local. Obter aprovação explícita para o banco-alvo e o impacto de logout.

## Checklist de execução autorizado

Responsável pela operação, em cada ambiente (incluindo homologação e produção):

1. Obter aprovação e agendar janela. Inventariar todos os ambientes e instâncias que compartilham a chave, o banco correspondente e quem pode revogar sessões. Capturar, em cliente de teste controlado, um cookie de sessão web **já existente** para a verificação posterior; não registrar nem exportar o cookie.
2. Gerar uma nova chave aleatória forte em um gerenciador de segredos confiável (no mínimo 32 bytes). Não reutilizar a chave JWT. Verificar reutilização da chave anterior em outros serviços sem revelar seu valor; planejar a rotação de cada reutilização.
3. Suspender/drenar o tráfego do ambiente. Atualizar `FLASK_SECRET_KEY` apenas na configuração segura de runtime (`.env` local ignorado pelo Git ou secret manager do ambiente). Não usar Dockerfile `ARG`/`ENV`, commits, tickets ou mensagens para transportar o valor.
4. Reconstruir a imagem quando houver código novo a implantar; a rotação isolada da chave não exige embutir a chave no build. **Recriar** todos os contêineres/instâncias Flask/Gunicorn com a configuração nova. `docker restart` sozinho não reaplica alterações de `--env-file`. Não manter nós antigos atendendo ao mesmo tempo nem configurar fallback para a chave anterior.
5. Revogar as sessões persistentes antigas em uma janela de manutenção, usando conta administrativa do banco e transação auditada. Confirmar o banco/ambiente alvo e o impacto de logout global antes de executar. Exemplo de operação **somente após autorização explícita**:

   ```sql
   BEGIN;
   UPDATE auth_sessions
      SET revoked_at = clock_timestamp()
    WHERE revoked_at IS NULL;
   COMMIT;
   ```

   Isso encerra access/refresh tokens associados; os usuários precisarão autenticar novamente. Não executar essa instrução contra outro ambiente por engano. Se a operação falhar, fazer rollback e não declarar a rotação concluída.
6. Ainda antes de liberar o tráfego, conferir em cada instância apenas **presença/ausência** da variável e saúde do processo; nunca executar `env`, `printenv`, `docker inspect` completo ou logs de configuração. Confirmar `/health` e `/status`.
7. Com o cookie web controlado anterior à rotação, chamar uma rota web protegida: deve negar acesso. Com access e refresh tokens de sessão anterior, confirmar rejeição após a revogação no banco. Fazer novo login, acessar rota protegida, testar refresh e logout. Não colocar cookies/tokens em logs ou resultados de teste.
8. Liberar o tráfego somente depois de confirmar que todos os nós executam com a configuração nova. Registrar horário, ambientes cobertos, contagem de sessões revogadas e resultados, sem valores de segredo ou tokens.

## Histórico Git: decisão separada

Reescrever o histórico exigiria force-push coordenado e mudaria hashes de commits e tags. Pode quebrar clones, forks, branches, PRs, links, assinaturas e automações; cópias em caches ou clones externos podem continuar existindo. Portanto, purge não substitui rotação e não deve ser executado como parte automática desta operação. A equipe deve decidir separadamente se o benefício justifica o impacto, com plano para forks e caches.

O projeto ainda aceita cookies Flask para a interface web; essa compatibilidade exige um segredo Flask válido e único por ambiente. A autenticação moderna também revalida `auth_sessions` no banco, mas isso não substitui rotação e revogação após exposição. Os testes automatizados de configuração impedem ausência, placeholder, chave curta e reutilização da chave JWT no startup. Secret scanning em CI/pre-commit continua recomendado como defesa adicional, sem colocar valores reais em fixtures.
