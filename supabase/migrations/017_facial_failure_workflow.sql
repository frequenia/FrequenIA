begin;

alter table public.ocorrencias
    drop constraint ocorrencias_estado_check,
    drop constraint ocorrencias_check;

alter table public.ocorrencias
    add constraint ocorrencias_estado_check
        check (estado in ('aberta', 'em_analise', 'resolvida', 'arquivada', 'descartada')),
    add constraint ocorrencias_terminal_timestamp_check
        check (
            (estado in ('resolvida', 'descartada') and resolved_at is not null)
            or (estado not in ('resolvida', 'descartada') and resolved_at is null)
        ),
    add constraint ocorrencias_falha_facial_estado_check
        check (
            tipo <> 'falha_facial'
            or estado in ('aberta', 'em_analise', 'resolvida', 'descartada')
        ),
    add constraint ocorrencias_descartada_tipo_check
        check (estado <> 'descartada' or tipo = 'falha_facial'),
    add constraint ocorrencias_falha_facial_decisao_check
        check (
            tipo <> 'falha_facial'
            or estado not in ('resolvida', 'descartada')
            or (
                responsavel_usuario_id is not null
                and decisao is not null
                and decisao = btrim(decisao)
                and decisao <> ''
            )
        );

commit;
