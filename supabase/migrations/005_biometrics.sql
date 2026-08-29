begin;

create table public.biometrias (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    funcionario_id uuid not null,
    embedding extensions.vector(512) not null,
    modelo text not null,
    versao_modelo text not null,
    referencia_arquivo_privado text,
    status text not null default 'ativa'
        check (status in ('ativa', 'bloqueada', 'revogada')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint biometrias_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    check (modelo = btrim(modelo) and modelo <> ''),
    check (versao_modelo = btrim(versao_modelo) and versao_modelo <> ''),
    check (
        referencia_arquivo_privado is null
        or (referencia_arquivo_privado = btrim(referencia_arquivo_privado)
            and referencia_arquivo_privado <> '')
    ),
    check (
        (status = 'revogada' and revoked_at is not null)
        or (status <> 'revogada' and revoked_at is null)
    )
);

commit;
