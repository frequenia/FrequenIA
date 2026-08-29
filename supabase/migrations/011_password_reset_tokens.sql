begin;

alter table public.usuarios
    alter column senha_hash drop not null;

create table public.password_reset_tokens (
    id uuid primary key default extensions.gen_random_uuid(),
    usuario_id uuid not null,
    token_hash text not null unique,
    purpose text not null default 'password_reset'
        check (purpose in ('password_reset', 'first_access')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    used_at timestamptz,
    revoked_at timestamptz,
    constraint password_reset_tokens_usuario_fk
        foreign key (usuario_id) references public.usuarios(id) on delete restrict,
    check (token_hash ~ '^[0-9a-f]{64}$'),
    check (expires_at > created_at),
    check (used_at is null or used_at >= created_at),
    check (revoked_at is null or revoked_at >= created_at)
);

create index password_reset_tokens_usuario_created_idx
    on public.password_reset_tokens (usuario_id, created_at desc);

create index password_reset_tokens_active_idx
    on public.password_reset_tokens (usuario_id, expires_at)
    where used_at is null and revoked_at is null;

commit;
