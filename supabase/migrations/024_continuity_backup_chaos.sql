begin;

create table public.execucoes_continuidade (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid,
    tipo text not null,
    estado text not null default 'planejado',
    ambiente_logico text not null,
    responsavel_usuario_id uuid,
    responsavel_papel text,
    manifesto_versao smallint,
    evidencia_integridade_sha256 text,
    integridade_resultado text,
    itens_total bigint not null default 0,
    bytes_total bigint not null default 0,
    duracao_ms bigint,
    rpo_observado_segundos bigint,
    rto_observado_segundos bigint,
    erro_codigo text,
    iniciado_at timestamptz,
    concluido_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    constraint execucoes_continuidade_empresa_fk foreign key (empresa_id)
        references public.empresas(id),
    constraint execucoes_continuidade_responsavel_fk foreign key (responsavel_usuario_id)
        references public.usuarios(id),
    constraint execucoes_continuidade_tipo_check check (tipo in (
        'backup_teste','restore_teste','redrive_teste','caos_teste','capacidade_teste','tag_purge'
    )),
    constraint execucoes_continuidade_estado_check check (estado in (
        'planejado','executando','concluido','falha_reprocessavel','falha_terminal','cancelado'
    )),
    constraint execucoes_continuidade_ambiente_check check (
        ambiente_logico ~ '^(development|test|testing|staging)-?[a-z0-9-]{0,24}$'
    ),
    constraint execucoes_continuidade_papel_check check (
        responsavel_papel is null or responsavel_papel in ('sistema','admin','rh','operador')
    ),
    constraint execucoes_continuidade_sha_check check (
        evidencia_integridade_sha256 is null or evidencia_integridade_sha256 ~ '^[0-9a-f]{64}$'
    ),
    constraint execucoes_continuidade_integridade_check check (
        integridade_resultado is null or integridade_resultado in ('valido','invalido','parcial')
    ),
    constraint execucoes_continuidade_contagens_check check (
        itens_total >= 0 and bytes_total >= 0 and
        (duracao_ms is null or duracao_ms >= 0) and
        (rpo_observado_segundos is null or rpo_observado_segundos >= 0) and
        (rto_observado_segundos is null or rto_observado_segundos >= 0)
    ),
    constraint execucoes_continuidade_erro_check check (
        erro_codigo is null or erro_codigo ~ '^[a-z0-9_]{1,64}$'
    ),
    constraint execucoes_continuidade_terminal_check check (
        (estado = 'concluido' and concluido_at is not null and integridade_resultado = 'valido')
        or estado <> 'concluido'
    )
);

create index execucoes_continuidade_tipo_estado_idx
    on public.execucoes_continuidade (tipo, estado, created_at desc);
create index execucoes_continuidade_empresa_tipo_idx
    on public.execucoes_continuidade (empresa_id, tipo, created_at desc)
    where empresa_id is not null;

create table public.execucoes_continuidade_historico (
    id uuid primary key default gen_random_uuid(),
    execucao_id uuid not null references public.execucoes_continuidade(id),
    empresa_id uuid,
    estado text not null,
    resultado_codigo text not null,
    contagem bigint not null default 0,
    bytes_total bigint not null default 0,
    created_at timestamptz not null default clock_timestamp(),
    constraint execucoes_continuidade_historico_empresa_fk foreign key (empresa_id)
        references public.empresas(id),
    constraint execucoes_continuidade_historico_estado_check check (estado in (
        'planejado','executando','concluido','falha_reprocessavel','falha_terminal','cancelado'
    )),
    constraint execucoes_continuidade_historico_resultado_check check (
        resultado_codigo ~ '^[a-z0-9_]{1,64}$'
    ),
    constraint execucoes_continuidade_historico_contagens_check check (
        contagem >= 0 and bytes_total >= 0
    )
);

create index execucoes_continuidade_historico_execucao_idx
    on public.execucoes_continuidade_historico (execucao_id, created_at, id);

create or replace function public.prevent_continuity_history_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'continuity history is append-only';
end;
$$;

create trigger execucoes_continuidade_historico_append_only
before update or delete on public.execucoes_continuidade_historico
for each row execute function public.prevent_continuity_history_mutation();

alter table public.anexos_correcao
    add column preservacao_ate timestamptz,
    add column purge_autorizado_at timestamptz;

create table public.anexo_purge_tag_jobs (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null,
    anexo_id uuid not null,
    estado text not null default 'pendente',
    tentativas integer not null default 0,
    proxima_tentativa_at timestamptz not null default clock_timestamp(),
    erro_codigo text,
    aplicado_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    constraint anexo_purge_tag_jobs_anexo_fk foreign key (empresa_id, anexo_id)
        references public.anexos_correcao (empresa_id, id),
    constraint anexo_purge_tag_jobs_anexo_unique unique (anexo_id),
    constraint anexo_purge_tag_jobs_estado_check check (
        estado in ('pendente','processando','aplicado','falha_reprocessavel','cancelado')
    ),
    constraint anexo_purge_tag_jobs_tentativas_check check (tentativas >= 0),
    constraint anexo_purge_tag_jobs_erro_check check (
        erro_codigo is null or erro_codigo ~ '^[a-z0-9_]{1,64}$'
    ),
    constraint anexo_purge_tag_jobs_aplicado_check check (
        (estado = 'aplicado' and aplicado_at is not null) or estado <> 'aplicado'
    )
);

create index anexo_purge_tag_jobs_dispatch_idx
    on public.anexo_purge_tag_jobs (proxima_tentativa_at, created_at, id)
    where estado in ('pendente','falha_reprocessavel');
create index anexo_purge_tag_jobs_empresa_estado_idx
    on public.anexo_purge_tag_jobs (empresa_id, estado, updated_at);

comment on table public.execucoes_continuidade is
    'Controle sanitizado de exercícios; nunca contém dump, objeto, chave ou segredo.';
comment on table public.execucoes_continuidade_historico is
    'Histórico append-only dos exercícios de continuidade.';
comment on table public.anexo_purge_tag_jobs is
    'Outbox recuperável para aplicar tag S3 somente após autorização persistida.';

commit;
