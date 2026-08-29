begin;

create table public.turnos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    nome text not null,
    timezone text not null default 'America/Sao_Paulo',
    status text not null default 'ativo'
        check (status in ('ativo', 'inativo')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint turnos_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint turnos_empresa_id_id_unique unique (empresa_id, id),
    constraint turnos_empresa_nome_unique unique (empresa_id, nome),
    check (nome = btrim(nome) and nome <> ''),
    check (timezone = btrim(timezone) and timezone <> '')
);

create table public.periodos_turno (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    turno_id uuid not null,
    dia_semana smallint not null check (dia_semana between 0 and 6),
    ordem smallint not null check (ordem > 0),
    inicio time without time zone not null,
    fim time without time zone not null,
    fim_dia_offset smallint not null default 0
        check (fim_dia_offset in (0, 1)),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint periodos_turno_empresa_turno_fk
        foreign key (empresa_id, turno_id)
        references public.turnos (empresa_id, id) on delete restrict,
    constraint periodos_turno_turno_dia_ordem_unique
        unique (turno_id, dia_semana, ordem),
    check (fim_dia_offset = 1 or fim > inicio)
);

create table public.funcionarios_turnos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    turno_id uuid not null,
    vigencia_inicio date not null,
    vigencia_fim date,
    created_at timestamptz not null default now(),
    constraint funcionarios_turnos_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint funcionarios_turnos_empresa_turno_fk
        foreign key (empresa_id, turno_id)
        references public.turnos (empresa_id, id) on delete restrict,
    constraint funcionarios_turnos_funcionario_inicio_unique
        unique (funcionario_id, vigencia_inicio),
    check (vigencia_fim is null or vigencia_fim >= vigencia_inicio)
);

commit;
