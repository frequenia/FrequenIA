begin;

create table public.terminais_ponto (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    nome text not null,
    credencial_hash char(64) not null unique,
    status text not null default 'ativo'
        check (status in ('ativo', 'revogado')),
    created_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint terminais_ponto_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    check (nome = btrim(nome) and nome <> ''),
    check ((status = 'revogado') = (revoked_at is not null))
);

create index terminais_ponto_empresa_status_idx
    on public.terminais_ponto (empresa_id, status);

commit;
