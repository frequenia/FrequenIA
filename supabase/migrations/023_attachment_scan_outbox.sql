begin;

alter table public.anexos_correcao
    add constraint anexos_correcao_empresa_id_unique unique (empresa_id, id);

create table public.anexo_varredura_jobs (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid not null,
    anexo_id uuid not null,
    schema_versao smallint not null default 1,
    estado text not null default 'pendente_publicacao',
    publicacao_tentativas integer not null default 0,
    processamento_tentativas integer not null default 0,
    proxima_tentativa_at timestamptz not null default clock_timestamp(),
    publicado_at timestamptz,
    processamento_iniciado_at timestamptz,
    concluido_at timestamptz,
    mensagem_id text,
    erro_codigo text,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    constraint anexo_varredura_jobs_anexo_tenant_fk
        foreign key (empresa_id, anexo_id)
        references public.anexos_correcao (empresa_id, id),
    constraint anexo_varredura_jobs_anexo_unique unique (anexo_id),
    constraint anexo_varredura_jobs_schema_check check (schema_versao = 1),
    constraint anexo_varredura_jobs_estado_check check (estado in (
        'pendente_publicacao', 'publicado', 'processando', 'concluido',
        'falha_reprocessavel', 'falha_terminal'
    )),
    constraint anexo_varredura_jobs_tentativas_check check (
        publicacao_tentativas >= 0 and processamento_tentativas >= 0
    ),
    constraint anexo_varredura_jobs_mensagem_check check (
        mensagem_id is null or mensagem_id ~ '^[A-Za-z0-9._:-]{1,128}$'
    ),
    constraint anexo_varredura_jobs_erro_check check (
        erro_codigo is null or erro_codigo ~ '^[a-z0-9_]{1,64}$'
    )
);

create index anexo_varredura_jobs_dispatch_idx
    on public.anexo_varredura_jobs (proxima_tentativa_at, created_at, id)
    where estado in ('pendente_publicacao', 'falha_reprocessavel');

create index anexo_varredura_jobs_empresa_estado_idx
    on public.anexo_varredura_jobs (empresa_id, estado, updated_at);

create index anexo_varredura_jobs_anexo_empresa_idx
    on public.anexo_varredura_jobs (empresa_id, anexo_id);

comment on table public.anexo_varredura_jobs is
    'Outbox transacional e controle idempotente da varredura assíncrona de comprovantes.';
comment on column public.anexo_varredura_jobs.mensagem_id is
    'Identificador opaco retornado pela fila; nunca contém dados de usuário ou chave de objeto.';

commit;
