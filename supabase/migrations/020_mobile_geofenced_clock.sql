begin;

alter table public.unidades
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists endereco_geocodificado text,
    add column if not exists raio_metros integer not null default 150,
    add column if not exists marcacao_mobile_ativa boolean not null default false,
    add column if not exists geofence_updated_at timestamptz,
    add column if not exists geofence_updated_by uuid;

alter table public.unidades
    add constraint unidades_latitude_check
        check (latitude is null or latitude between -90 and 90),
    add constraint unidades_longitude_check
        check (longitude is null or longitude between -180 and 180),
    add constraint unidades_raio_metros_check
        check (raio_metros between 25 and 1000),
    add constraint unidades_mobile_configurada_check
        check (not marcacao_mobile_ativa or (latitude is not null and longitude is not null)),
    add constraint unidades_geofence_updated_by_fk
        foreign key (geofence_updated_by) references public.usuarios(id) on delete set null;

alter table public.marcacoes
    add column if not exists unidade_id uuid,
    add column if not exists canal text not null default 'legado',
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists precisao_metros double precision,
    add column if not exists distancia_unidade_metros double precision,
    add column if not exists localizacao_capturada_at timestamptz,
    add column if not exists endereco_localizacao text;

alter table public.marcacoes
    add constraint marcacoes_unidade_empresa_fk
        foreign key (empresa_id, unidade_id)
        references public.unidades (empresa_id, id) on delete restrict,
    add constraint marcacoes_canal_check
        check (canal in ('legado', 'quiosque', 'mobile', 'administrativo', 'importacao')),
    add constraint marcacoes_latitude_check
        check (latitude is null or latitude between -90 and 90),
    add constraint marcacoes_longitude_check
        check (longitude is null or longitude between -180 and 180),
    add constraint marcacoes_precisao_check
        check (precisao_metros is null or precisao_metros >= 0),
    add constraint marcacoes_distancia_check
        check (distancia_unidade_metros is null or distancia_unidade_metros >= 0),
    add constraint marcacoes_mobile_localizacao_check
        check (
            canal <> 'mobile'
            or (
                unidade_id is not null
                and latitude is not null
                and longitude is not null
                and precisao_metros is not null
                and distancia_unidade_metros is not null
                and localizacao_capturada_at is not null
            )
        );

create index if not exists marcacoes_empresa_unidade_instante_idx
    on public.marcacoes (empresa_id, unidade_id, instante desc);

comment on column public.unidades.marcacao_mobile_ativa is
    'Habilita marcação facial mobile somente após configuração explícita da geofence.';
comment on column public.marcacoes.endereco_localizacao is
    'Snapshot opcional do endereço TomTom; não participa da autorização.';

commit;
