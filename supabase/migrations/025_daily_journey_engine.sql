begin;

create table public.escalas_diarias (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    data_operacional date not null,
    tipo text not null check (tipo in ('turno', 'folga')),
    origem text not null check (origem in ('escala', 'troca', 'ajuste')),
    turno_id uuid,
    justificativa text not null,
    criado_por_usuario_id uuid not null,
    cancelado_por_usuario_id uuid,
    cancelamento_justificativa text,
    cancelado_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    constraint escalas_diarias_funcionario_fk foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint escalas_diarias_turno_fk foreign key (empresa_id, turno_id)
        references public.turnos (empresa_id, id) on delete restrict,
    constraint escalas_diarias_criador_fk foreign key (criado_por_usuario_id)
        references public.usuarios (id) on delete restrict,
    constraint escalas_diarias_cancelador_fk foreign key (cancelado_por_usuario_id)
        references public.usuarios (id) on delete restrict,
    constraint escalas_diarias_justificativa_check check (
        justificativa = btrim(justificativa) and justificativa <> ''
    ),
    constraint escalas_diarias_tipo_turno_check check (
        (tipo = 'turno' and turno_id is not null)
        or (tipo = 'folga' and turno_id is null)
    ),
    constraint escalas_diarias_cancelamento_check check (
        (cancelado_at is null and cancelado_por_usuario_id is null
            and cancelamento_justificativa is null)
        or (cancelado_at is not null and cancelado_por_usuario_id is not null
            and cancelamento_justificativa = btrim(cancelamento_justificativa)
            and cancelamento_justificativa <> '')
    ),
    constraint escalas_diarias_empresa_id_id_unique unique (empresa_id, id)
);

create unique index escalas_diarias_ativa_unique
    on public.escalas_diarias (empresa_id, funcionario_id, data_operacional)
    where cancelado_at is null;
create index escalas_diarias_consulta_idx
    on public.escalas_diarias (empresa_id, funcionario_id, data_operacional, created_at desc);

create table public.jornadas_diarias (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    data_operacional date not null,
    timezone text not null,
    origem text not null,
    turno_id uuid,
    escala_diaria_id uuid,
    atribuicao_turno_id uuid,
    versao smallint not null default 1 check (versao > 0),
    created_at timestamptz not null default clock_timestamp(),
    constraint jornadas_diarias_funcionario_fk foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint jornadas_diarias_turno_fk foreign key (empresa_id, turno_id)
        references public.turnos (empresa_id, id) on delete restrict,
    constraint jornadas_diarias_escala_fk foreign key (empresa_id, escala_diaria_id)
        references public.escalas_diarias (empresa_id, id) on delete restrict,
    constraint jornadas_diarias_atribuicao_fk foreign key (atribuicao_turno_id)
        references public.funcionarios_turnos (id) on delete restrict,
    constraint jornadas_diarias_timezone_check check (timezone = btrim(timezone) and timezone <> ''),
    constraint jornadas_diarias_origem_check check (
        (origem in ('folga', 'sem_jornada') and turno_id is null)
        or (origem in ('turno', 'escala', 'troca', 'ajuste') and turno_id is not null)
    ),
    constraint jornadas_diarias_empresa_id_id_unique unique (empresa_id, id),
    constraint jornadas_diarias_empresa_funcionario_data_unique
        unique (empresa_id, funcionario_id, data_operacional)
);

create table public.jornada_eventos_esperados (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    jornada_id uuid not null,
    ordem smallint not null check (ordem > 0),
    tipo text not null check (tipo in ('entrada', 'saida_intervalo', 'retorno_intervalo', 'saida')),
    instante_esperado timestamptz not null,
    marcacao_id uuid,
    cumprido_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    constraint jornada_eventos_jornada_fk foreign key (empresa_id, jornada_id)
        references public.jornadas_diarias (empresa_id, id) on delete restrict,
    constraint jornada_eventos_marcacao_fk foreign key (empresa_id, marcacao_id)
        references public.marcacoes (empresa_id, id) on delete restrict,
    constraint jornada_eventos_cumprido_check check (
        (marcacao_id is null and cumprido_at is null)
        or (marcacao_id is not null and cumprido_at is not null)
    ),
    constraint jornada_eventos_empresa_id_id_unique unique (empresa_id, id),
    constraint jornada_eventos_ordem_unique unique (jornada_id, ordem),
    constraint jornada_eventos_marcacao_unique unique (marcacao_id)
);

create index jornada_eventos_proximo_idx
    on public.jornada_eventos_esperados (empresa_id, jornada_id, ordem);

alter table public.marcacoes
    add column jornada_evento_id uuid,
    add constraint marcacoes_jornada_evento_fk foreign key (empresa_id, jornada_evento_id)
        references public.jornada_eventos_esperados (empresa_id, id) on delete restrict;

create unique index marcacoes_jornada_evento_unique
    on public.marcacoes (jornada_evento_id)
    where jornada_evento_id is not null;

create table public.tentativas_jornada (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    jornada_id uuid,
    evento_esperado_id uuid,
    tentativa_facial_id uuid,
    chave_idempotencia uuid not null,
    canal text not null check (canal in ('mobile', 'quiosque')),
    resultado text not null check (resultado in ('confirmada', 'analise', 'bloqueada')),
    motivo_codigo text not null check (motivo_codigo ~ '^[a-z0-9_]{1,64}$'),
    tipo_legado text,
    created_at timestamptz not null default clock_timestamp(),
    constraint tentativas_jornada_funcionario_fk foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    constraint tentativas_jornada_jornada_fk foreign key (empresa_id, jornada_id)
        references public.jornadas_diarias (empresa_id, id) on delete restrict,
    constraint tentativas_jornada_evento_fk foreign key (empresa_id, evento_esperado_id)
        references public.jornada_eventos_esperados (empresa_id, id) on delete restrict,
    constraint tentativas_jornada_facial_fk foreign key (empresa_id, funcionario_id, tentativa_facial_id)
        references public.tentativas_faciais (empresa_id, funcionario_id, id) on delete restrict,
    constraint tentativas_jornada_tipo_legado_check check (
        tipo_legado is null or tipo_legado in ('entrada', 'saida_intervalo', 'retorno_intervalo', 'saida')
    ),
    constraint tentativas_jornada_empresa_id_id_unique unique (empresa_id, id),
    constraint tentativas_jornada_idempotencia_unique unique (empresa_id, chave_idempotencia)
);

create index tentativas_jornada_ciclo_idx
    on public.tentativas_jornada (empresa_id, funcionario_id, jornada_id, evento_esperado_id, created_at desc);

alter table public.ocorrencias
    add column jornada_id uuid,
    add column jornada_evento_id uuid,
    add column data_operacional date,
    add column motivo_codigo text,
    add constraint ocorrencias_jornada_fk foreign key (empresa_id, jornada_id)
        references public.jornadas_diarias (empresa_id, id) on delete restrict,
    add constraint ocorrencias_jornada_evento_fk foreign key (empresa_id, jornada_evento_id)
        references public.jornada_eventos_esperados (empresa_id, id) on delete restrict,
    add constraint ocorrencias_ordem_motivo_check check (
        motivo_codigo is null or motivo_codigo ~ '^[a-z0-9_]{1,64}$'
    );

create unique index ocorrencias_ordem_ciclo_unique
    on public.ocorrencias (
        empresa_id, funcionario_id, data_operacional, motivo_codigo,
        coalesce(jornada_evento_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    where tipo = 'ordem_invalida' and estado in ('aberta', 'em_analise');

create or replace function public.proteger_jornada_snapshot()
returns trigger language plpgsql as $$
begin
    raise exception 'daily journey snapshot is immutable';
end;
$$;

create trigger jornadas_diarias_immutable
before update or delete on public.jornadas_diarias
for each row execute function public.proteger_jornada_snapshot();

create or replace function public.proteger_evento_jornada()
returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'daily journey event is immutable';
    end if;
    if old.empresa_id <> new.empresa_id
       or old.jornada_id <> new.jornada_id
       or old.ordem <> new.ordem
       or old.tipo <> new.tipo
       or old.instante_esperado <> new.instante_esperado
       or old.created_at <> new.created_at
       or old.marcacao_id is not null
       or new.marcacao_id is null
       or new.cumprido_at is null then
        raise exception 'daily journey event plan is immutable';
    end if;
    return new;
end;
$$;

create trigger jornada_eventos_immutable
before update or delete on public.jornada_eventos_esperados
for each row execute function public.proteger_evento_jornada();

comment on table public.jornadas_diarias is
    'Snapshot técnico imutável; não substitui marcações nem a visão efetiva.';
comment on table public.tentativas_jornada is
    'Tentativas técnicas sanitizadas, inclusive quando nenhuma marcação é confirmada.';

commit;
