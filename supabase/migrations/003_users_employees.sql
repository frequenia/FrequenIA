begin;

create table public.usuarios (
    id uuid primary key default extensions.gen_random_uuid(),
    nome text not null,
    cpf text not null unique,
    email text unique,
    telefone text,
    senha_hash text not null,
    status text not null default 'ativo'
        check (status in ('ativo', 'bloqueado', 'inativo')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (nome = btrim(nome) and nome <> ''),
    check (cpf ~ '^[0-9]{11}$'),
    check (email is null or (email = lower(btrim(email)) and email <> '')),
    check (telefone is null or telefone = btrim(telefone)),
    check (senha_hash <> '')
);

create table public.funcionarios (
    id uuid primary key default extensions.gen_random_uuid(),
    usuario_id uuid not null,
    empresa_id uuid not null,
    unidade_id uuid not null,
    equipe_id uuid,
    cargo_id uuid,
    matricula text not null,
    data_admissao date,
    tipo_contrato text,
    carga_horaria_semanal numeric(5,2),
    perfil text not null default 'funcionario'
        check (perfil in ('funcionario', 'gestor', 'rh', 'administrador')),
    status text not null default 'ativo'
        check (status in ('ativo', 'afastado', 'desligado')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint funcionarios_usuario_fk
        foreign key (usuario_id) references public.usuarios(id) on delete restrict,
    constraint funcionarios_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint funcionarios_unidade_empresa_fk
        foreign key (empresa_id, unidade_id)
        references public.unidades (empresa_id, id) on delete restrict,
    constraint funcionarios_equipe_empresa_unidade_fk
        foreign key (empresa_id, unidade_id, equipe_id)
        references public.equipes (empresa_id, unidade_id, id) on delete restrict,
    constraint funcionarios_cargo_empresa_fk
        foreign key (empresa_id, cargo_id)
        references public.cargos (empresa_id, id) on delete restrict,
    constraint funcionarios_empresa_id_id_unique unique (empresa_id, id),
    constraint funcionarios_empresa_usuario_unique unique (empresa_id, usuario_id),
    constraint funcionarios_empresa_matricula_unique unique (empresa_id, matricula),
    check (matricula = btrim(matricula) and matricula <> ''),
    check (tipo_contrato is null or tipo_contrato in (
        'efetivo', 'comissionado', 'temporario', 'estagiario', 'terceirizado', 'outro'
    )),
    check (
        carga_horaria_semanal is null
        or (carga_horaria_semanal > 0 and carga_horaria_semanal <= 168)
    )
);

commit;
