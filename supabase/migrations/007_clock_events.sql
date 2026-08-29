begin;

create table public.tentativas_faciais (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    instante timestamptz not null default now(),
    resultado text not null
        check (resultado in ('sucesso', 'falha', 'bloqueada', 'expirada')),
    motivo_codigo text,
    distancia_facial double precision,
    created_at timestamptz not null default now(),
    constraint tentativas_faciais_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint tentativas_faciais_empresa_funcionario_id_unique
        unique (empresa_id, funcionario_id, id),
    check (motivo_codigo is null or motivo_codigo ~ '^[a-z0-9_]{1,64}$'),
    check (distancia_facial is null or distancia_facial >= 0)
);

create table public.marcacoes (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    tentativa_facial_id uuid,
    instante timestamptz not null,
    tipo text not null
        check (tipo in ('entrada', 'saida_intervalo', 'retorno_intervalo', 'saida')),
    origem text not null
        check (origem in ('facial', 'manual', 'importada')),
    estado text not null default 'confirmada'
        check (estado in ('confirmada', 'pendente', 'rejeitada')),
    chave_idempotencia uuid not null default extensions.gen_random_uuid(),
    created_at timestamptz not null default now(),
    constraint marcacoes_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint marcacoes_empresa_funcionario_tentativa_fk
        foreign key (empresa_id, funcionario_id, tentativa_facial_id)
        references public.tentativas_faciais (empresa_id, funcionario_id, id)
        on delete restrict,
    constraint marcacoes_empresa_id_id_unique unique (empresa_id, id),
    constraint marcacoes_empresa_funcionario_id_unique
        unique (empresa_id, funcionario_id, id),
    constraint marcacoes_empresa_idempotencia_unique
        unique (empresa_id, chave_idempotencia),
    check (
        (origem = 'facial' and tentativa_facial_id is not null)
        or (origem <> 'facial' and tentativa_facial_id is null)
    )
);

commit;
