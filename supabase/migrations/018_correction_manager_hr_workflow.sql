begin;

alter table public.correcoes
    alter column estado set default 'pendente_gestor';

alter table public.correcoes
    drop constraint if exists correcoes_estado_check;

update public.correcoes
set estado = case
    when estado in ('solicitada', 'em_analise_gestor') then 'pendente_gestor'
    when estado in ('encaminhada_rh', 'em_analise_rh') then 'encaminhada_rh'
    else estado
end
where estado in ('solicitada', 'em_analise_gestor', 'encaminhada_rh', 'em_analise_rh');

alter table public.correcoes
    add constraint correcoes_estado_check
    check (estado in (
        'pendente_gestor', 'encaminhada_rh', 'aprovada', 'rejeitada', 'cancelada'
    ));

create index correcoes_empresa_estado_data_idx
    on public.correcoes (empresa_id, estado, created_at desc);

comment on column public.correcoes.estado is
    'Workflow Fase 24: pendente_gestor -> aprovada/rejeitada/encaminhada_rh; encaminhada_rh -> aprovada/rejeitada; pendente_gestor -> cancelada pelo solicitante.';

commit;
