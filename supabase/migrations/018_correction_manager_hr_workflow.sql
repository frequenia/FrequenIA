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

-- A constraint original da migration 008 exigia texto de decisao tanto para
-- rejeicao quanto para aprovacao. No workflow Gestor -> RH a observacao de
-- aprovacao e opcional, enquanto a rejeicao continua obrigatoriamente
-- justificada. O nome automatico da constraint varia conforme a versao e o
-- historico do PostgreSQL, por isso ela e localizada pela definicao.
do $$
declare
    legacy_constraint record;
begin
    for legacy_constraint in
        select conname
        from pg_constraint
        where conrelid = 'public.correcoes'::regclass
          and contype = 'c'
          and pg_get_constraintdef(oid) like '%responsavel_decisao_usuario_id IS NOT NULL%'
          and pg_get_constraintdef(oid) like '%decided_at IS NOT NULL%'
          and pg_get_constraintdef(oid) like '%decisao IS NOT NULL%'
    loop
        execute format(
            'alter table public.correcoes drop constraint %I',
            legacy_constraint.conname
        );
    end loop;
end
$$;

alter table public.correcoes
    add constraint correcoes_decisao_estado_check
    check (
        estado not in ('aprovada', 'rejeitada')
        or (
            responsavel_decisao_usuario_id is not null
            and decided_at is not null
            and (
                estado <> 'rejeitada'
                or (
                    decisao is not null
                    and decisao = btrim(decisao)
                    and decisao <> ''
                )
            )
        )
    );

create index correcoes_empresa_estado_data_idx
    on public.correcoes (empresa_id, estado, created_at desc);

comment on column public.correcoes.estado is
    'Workflow Fase 24: pendente_gestor -> aprovada/rejeitada/encaminhada_rh; encaminhada_rh -> aprovada/rejeitada; pendente_gestor -> cancelada pelo solicitante.';

commit;
