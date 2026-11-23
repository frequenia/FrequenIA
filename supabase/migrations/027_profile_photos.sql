begin;
-- Avatar opcional e privado. Não integra o cadastro biométrico.
create table public.fotos_perfil (
    usuario_id uuid primary key references public.usuarios(id) on delete cascade,
    conteudo bytea not null check (octet_length(conteudo) between 1 and 262144),
    updated_at timestamptz not null default clock_timestamp()
);
alter table public.fotos_perfil enable row level security;
revoke all on public.fotos_perfil from public, anon, authenticated;
comment on table public.fotos_perfil is
    'Avatar JPEG reprocessado, sem metadados. Acesso somente pelo backend à própria conta; nunca usado para reconhecimento facial.';
commit;
