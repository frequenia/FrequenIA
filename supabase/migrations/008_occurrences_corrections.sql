begin;

create table public.ocorrencias (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    tentativa_facial_id uuid,
    marcacao_id uuid,
    tipo text not null
        check (tipo in ('falha_facial', 'ordem_invalida', 'outra')),
    descricao text,
    estado text not null default 'aberta'
        check (estado in ('aberta', 'em_analise', 'resolvida', 'arquivada')),
    primeira_ocorrencia_at timestamptz not null,
    responsavel_usuario_id uuid,
    decisao text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    resolved_at timestamptz,
    constraint ocorrencias_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint ocorrencias_empresa_funcionario_tentativa_fk
        foreign key (empresa_id, funcionario_id, tentativa_facial_id)
        references public.tentativas_faciais (empresa_id, funcionario_id, id)
        on delete restrict,
    constraint ocorrencias_empresa_funcionario_marcacao_fk
        foreign key (empresa_id, funcionario_id, marcacao_id)
        references public.marcacoes (empresa_id, funcionario_id, id)
        on delete restrict,
    constraint ocorrencias_responsavel_fk
        foreign key (responsavel_usuario_id)
        references public.usuarios(id) on delete restrict,
    check (descricao is null or descricao <> ''),
    check (
        (estado = 'resolvida' and resolved_at is not null)
        or (estado <> 'resolvida' and resolved_at is null)
    )
);

create table public.correcoes (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    marcacao_original_id uuid,
    solicitante_usuario_id uuid not null,
    responsavel_decisao_usuario_id uuid,
    tipo text not null
        check (tipo in ('inclusao', 'alteracao_instante', 'alteracao_tipo', 'justificativa')),
    instante_proposto timestamptz,
    tipo_marcacao_proposto text
        check (tipo_marcacao_proposto is null or tipo_marcacao_proposto in (
            'entrada', 'saida_intervalo', 'retorno_intervalo', 'saida'
        )),
    motivo text not null,
    estado text not null default 'solicitada'
        check (estado in (
            'solicitada', 'em_analise_gestor', 'encaminhada_rh',
            'em_analise_rh', 'aprovada', 'rejeitada', 'cancelada'
        )),
    decisao text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    decided_at timestamptz,
    constraint correcoes_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint correcoes_empresa_funcionario_marcacao_fk
        foreign key (empresa_id, funcionario_id, marcacao_original_id)
        references public.marcacoes (empresa_id, funcionario_id, id)
        on delete restrict,
    constraint correcoes_solicitante_fk
        foreign key (solicitante_usuario_id)
        references public.usuarios(id) on delete restrict,
    constraint correcoes_responsavel_decisao_fk
        foreign key (responsavel_decisao_usuario_id)
        references public.usuarios(id) on delete restrict,
    check (motivo = btrim(motivo) and motivo <> ''),
    check (
        tipo <> 'inclusao'
        or (marcacao_original_id is null and instante_proposto is not null
            and tipo_marcacao_proposto is not null)
    ),
    check (
        tipo <> 'alteracao_instante'
        or (marcacao_original_id is not null and instante_proposto is not null)
    ),
    check (
        tipo <> 'alteracao_tipo'
        or (marcacao_original_id is not null and tipo_marcacao_proposto is not null)
    ),
    check (
        estado not in ('aprovada', 'rejeitada')
        or (responsavel_decisao_usuario_id is not null and decided_at is not null
            and decisao is not null)
    )
);

commit;
