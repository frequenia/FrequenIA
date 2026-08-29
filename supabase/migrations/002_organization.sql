begin;

create table public.empresas (
    id uuid primary key default extensions.gen_random_uuid(),
    nome text not null,
    cnpj text unique,
    status text not null default 'ativa'
        check (status in ('ativa', 'inativa')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (nome = btrim(nome) and nome <> ''),
    check (cnpj is null or cnpj ~ '^[0-9]{14}$')
);

create table public.unidades (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    nome text not null,
    codigo text,
    timezone text not null default 'America/Sao_Paulo',
    status text not null default 'ativa'
        check (status in ('ativa', 'inativa')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint unidades_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint unidades_empresa_id_id_unique unique (empresa_id, id),
    constraint unidades_empresa_nome_unique unique (empresa_id, nome),
    check (nome = btrim(nome) and nome <> ''),
    check (codigo is null or (codigo = btrim(codigo) and codigo <> '')),
    check (timezone = btrim(timezone) and timezone <> '')
);

create unique index unidades_empresa_codigo_unique
    on public.unidades (empresa_id, codigo)
    where codigo is not null;

create table public.equipes (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    unidade_id uuid not null,
    nome text not null,
    status text not null default 'ativa'
        check (status in ('ativa', 'inativa')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint equipes_unidade_empresa_fk
        foreign key (empresa_id, unidade_id)
        references public.unidades (empresa_id, id) on delete restrict,
    constraint equipes_empresa_id_id_unique unique (empresa_id, id),
    constraint equipes_empresa_unidade_id_id_unique
        unique (empresa_id, unidade_id, id),
    constraint equipes_unidade_nome_unique unique (unidade_id, nome),
    check (nome = btrim(nome) and nome <> '')
);

create table public.cargos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    nome text not null,
    status text not null default 'ativo'
        check (status in ('ativo', 'inativo')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint cargos_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint cargos_empresa_id_id_unique unique (empresa_id, id),
    constraint cargos_empresa_nome_unique unique (empresa_id, nome),
    check (nome = btrim(nome) and nome <> '')
);

commit;
