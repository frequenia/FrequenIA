begin;

-- Uma linha com equipe_id nulo delega toda a unidade; uma linha com equipe_id
-- limita o gestor à equipe indicada. As FKs compostas preservam o tenant.
create table public.gestores_escopos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    gestor_funcionario_id uuid not null,
    unidade_id uuid not null,
    equipe_id uuid,
    created_at timestamptz not null default now(),
    constraint gestores_escopos_gestor_empresa_fk
        foreign key (empresa_id, gestor_funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint gestores_escopos_unidade_empresa_fk
        foreign key (empresa_id, unidade_id)
        references public.unidades (empresa_id, id) on delete restrict,
    constraint gestores_escopos_equipe_empresa_unidade_fk
        foreign key (empresa_id, unidade_id, equipe_id)
        references public.equipes (empresa_id, unidade_id, id) on delete restrict
);

create unique index gestores_escopos_unidade_unique
    on public.gestores_escopos (empresa_id, gestor_funcionario_id, unidade_id)
    where equipe_id is null;

create unique index gestores_escopos_equipe_unique
    on public.gestores_escopos (
        empresa_id, gestor_funcionario_id, unidade_id, equipe_id
    )
    where equipe_id is not null;

create index gestores_escopos_lookup_idx
    on public.gestores_escopos (
        empresa_id, gestor_funcionario_id, unidade_id, equipe_id
    );

commit;
