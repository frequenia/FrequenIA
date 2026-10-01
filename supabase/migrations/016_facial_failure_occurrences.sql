begin;

alter table public.ocorrencias
    add column ciclo_falha_facial_id uuid;

create unique index ocorrencias_falha_facial_ciclo_unique
    on public.ocorrencias (empresa_id, funcionario_id, ciclo_falha_facial_id)
    where ciclo_falha_facial_id is not null;

alter table public.tentativas_faciais
    add column ocorrencia_id uuid,
    add column consumida_at timestamptz;

alter table public.tentativas_faciais
    add constraint tentativas_faciais_ocorrencia_fk
        foreign key (ocorrencia_id) references public.ocorrencias(id) on delete restrict,
    add constraint tentativas_faciais_consumida_check
        check ((ocorrencia_id is null) = (consumida_at is null));

create index tentativas_faciais_ciclo_falha_idx
    on public.tentativas_faciais (empresa_id, funcionario_id, instante, id)
    where ocorrencia_id is null
      and resultado = 'falha'
      and motivo_codigo in ('liveness_reprovado', 'nao_corresponde');

commit;
