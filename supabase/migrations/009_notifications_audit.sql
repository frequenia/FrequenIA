begin;

create table public.notificacoes (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid,
    usuario_id uuid not null,
    tipo text not null default 'sistema'
        check (tipo in ('sistema', 'marcacao', 'ocorrencia', 'correcao')),
    titulo text not null,
    mensagem text not null,
    created_at timestamptz not null default now(),
    read_at timestamptz,
    constraint notificacoes_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint notificacoes_usuario_fk
        foreign key (usuario_id) references public.usuarios(id) on delete restrict,
    check (titulo = btrim(titulo) and titulo <> ''),
    check (mensagem = btrim(mensagem) and mensagem <> ''),
    check (read_at is null or read_at >= created_at)
);

create table public.auditoria (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid,
    ator_usuario_id uuid,
    acao text not null,
    entidade_tipo text not null,
    entidade_id uuid,
    ocorrido_at timestamptz not null default now(),
    metadados jsonb not null default '{}'::jsonb,
    constraint auditoria_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint auditoria_ator_fk
        foreign key (ator_usuario_id) references public.usuarios(id) on delete set null,
    check (acao ~ '^[a-z0-9_.-]{1,100}$'),
    check (entidade_tipo ~ '^[a-z0-9_.-]{1,100}$'),
    check (jsonb_typeof(metadados) = 'object'),
    check (not (metadados ?| array[
        'senha', 'password', 'token', 'refresh_token', 'embedding',
        'foto', 'imagem', 'secret', 'segredo'
    ]))
);

commit;
