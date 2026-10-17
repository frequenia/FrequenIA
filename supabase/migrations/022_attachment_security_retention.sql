begin;

alter table public.anexos_correcao
    add column estado_seguranca text not null default 'quarentena',
    add column scan_tentativas integer not null default 0,
    add column scan_iniciado_at timestamptz,
    add column scan_concluido_at timestamptz,
    add column scan_resultado_codigo text,
    add column retencao_ate timestamptz,
    add column purge_tentativas integer not null default 0,
    add column purge_erro_codigo text,
    add column purgado_at timestamptz;

alter table public.anexos_correcao
    drop constraint anexos_correcao_chave_objeto_check,
    add constraint anexos_correcao_chave_objeto_check check (
        chave_objeto ~ '^correcoes/[0-9a-f-]{36}\.(pdf|jpg|png)$'
        or chave_objeto ~ '^[a-z0-9-]{1,32}/[0-9a-f-]{36}/(quarantine|clean)/[0-9a-f-]{36}\.(pdf|jpg|png)$'
    );

alter table public.anexos_correcao
    add constraint anexos_correcao_seguranca_check
        check (estado_seguranca in ('quarentena','limpo','infectado','erro_varredura')),
    add constraint anexos_correcao_scan_tentativas_check
        check (scan_tentativas >= 0),
    add constraint anexos_correcao_purge_tentativas_check
        check (purge_tentativas >= 0),
    add constraint anexos_correcao_scan_resultado_check
        check (scan_resultado_codigo is null or scan_resultado_codigo ~ '^[a-z0-9_]{1,64}$'),
    add constraint anexos_correcao_purge_erro_check
        check (purge_erro_codigo is null or purge_erro_codigo ~ '^[a-z0-9_]{1,64}$'),
    add constraint anexos_correcao_purgado_check
        check (purgado_at is null or estado <> 'ativo');

-- Registros da Fase 26 já foram validados antes de serem disponibilizados.
update public.anexos_correcao
set estado_seguranca = 'limpo',
    scan_tentativas = 1,
    scan_concluido_at = created_at,
    scan_resultado_codigo = 'migrado_fase26';

create index anexos_correcao_purge_idx
    on public.anexos_correcao (retencao_ate, id)
    where estado <> 'ativo' and purgado_at is null and retencao_ate is not null;

create index anexos_correcao_quarentena_idx
    on public.anexos_correcao (estado_seguranca, created_at)
    where estado = 'ativo' and estado_seguranca <> 'limpo';

commit;
