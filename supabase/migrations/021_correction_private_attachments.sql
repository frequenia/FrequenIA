begin;

alter table public.correcoes
    add constraint correcoes_empresa_funcionario_id_unique
        unique (empresa_id, funcionario_id, id);

create table public.anexos_correcao (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    correcao_id uuid not null,
    funcionario_id uuid not null,
    enviado_por_usuario_id uuid not null,
    chave_objeto text not null,
    nome_original text not null,
    tipo_mime text not null,
    tamanho_bytes bigint not null,
    sha256 text not null,
    estado text not null default 'ativo',
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    removed_at timestamptz,
    constraint anexos_correcao_empresa_funcionario_correcao_fk
        foreign key (empresa_id, funcionario_id, correcao_id)
        references public.correcoes (empresa_id, funcionario_id, id)
        on delete restrict,
    constraint anexos_correcao_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id)
        on delete restrict,
    constraint anexos_correcao_enviado_por_fk
        foreign key (enviado_por_usuario_id)
        references public.usuarios (id)
        on delete restrict,
    constraint anexos_correcao_chave_objeto_check
        check (chave_objeto ~ '^correcoes/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|jpg|png)$'),
    constraint anexos_correcao_nome_check
        check (
            nome_original = btrim(nome_original)
            and nome_original <> ''
            and char_length(nome_original) <= 200
        ),
    constraint anexos_correcao_mime_check
        check (tipo_mime in ('application/pdf', 'image/jpeg', 'image/png')),
    constraint anexos_correcao_tamanho_check
        check (tamanho_bytes between 1 and 10485760),
    constraint anexos_correcao_sha256_check
        check (sha256 ~ '^[0-9a-f]{64}$'),
    constraint anexos_correcao_estado_check
        check (estado in ('ativo', 'substituido', 'removido')),
    constraint anexos_correcao_remocao_check
        check (
            (estado = 'removido' and removed_at is not null)
            or (estado <> 'removido' and removed_at is null)
        )
);

create unique index anexos_correcao_ativo_unique
    on public.anexos_correcao (empresa_id, correcao_id)
    where estado = 'ativo';

create index anexos_correcao_empresa_correcao_idx
    on public.anexos_correcao (empresa_id, correcao_id, estado, created_at desc);

comment on table public.anexos_correcao is
    'Metadados privados e historicos do comprovante opcional; o binario permanece fora do banco.';

commit;
