begin;

alter table public.correcoes
    add column categoria text not null default 'outro'
        check (categoria in (
            'esquecimento_marcacao', 'horario_incorreto', 'tipo_incorreto',
            'justificativa', 'outro'
        ));

comment on column public.correcoes.categoria is
    'Categoria funcional informada pelo solicitante; tipo representa a operação efetiva.';

create index correcoes_empresa_funcionario_estado_data_idx
    on public.correcoes (empresa_id, funcionario_id, estado, created_at desc);

create index correcoes_empresa_categoria_data_idx
    on public.correcoes (empresa_id, categoria, created_at desc);

create unique index correcoes_aprovadas_marcacao_operacao_unique
    on public.correcoes (empresa_id, marcacao_original_id, tipo)
    where estado = 'aprovada'
      and marcacao_original_id is not null
      and tipo in ('alteracao_instante', 'alteracao_tipo');

commit;
