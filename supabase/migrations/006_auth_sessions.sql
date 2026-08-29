begin;

create table public.auth_sessions (
    id uuid primary key default extensions.gen_random_uuid(),
    usuario_id uuid not null,
    empresa_id uuid,
    funcionario_id uuid,
    refresh_token_hash text not null unique,
    familia_id uuid not null default extensions.gen_random_uuid(),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    last_used_at timestamptz,
    rotated_at timestamptz,
    revoked_at timestamptz,
    constraint auth_sessions_usuario_fk
        foreign key (usuario_id) references public.usuarios(id) on delete restrict,
    constraint auth_sessions_empresa_funcionario_fk
        foreign key (empresa_id, funcionario_id)
        references public.funcionarios (empresa_id, id) on delete restrict,
    check (length(refresh_token_hash) >= 32),
    check (
        (empresa_id is null and funcionario_id is null)
        or (empresa_id is not null and funcionario_id is not null)
    ),
    check (expires_at > created_at),
    check (last_used_at is null or last_used_at >= created_at),
    check (rotated_at is null or rotated_at >= created_at),
    check (revoked_at is null or revoked_at >= created_at)
);

commit;
