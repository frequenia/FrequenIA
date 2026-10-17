begin;

alter table public.usuarios
    add column perfil_sistema text,
    add column primeiro_acesso_pendente boolean not null default false,
    add constraint usuarios_perfil_sistema_check
        check (perfil_sistema is null or perfil_sistema = 'administrador_geral');

alter table public.cargos
    add column codigo_matricula text;

create unique index cargos_empresa_codigo_matricula_unique
    on public.cargos (empresa_id, codigo_matricula)
    where codigo_matricula is not null;

create table public.matriculas_sequencias (
    empresa_id uuid not null,
    cargo_id uuid not null,
    ultimo_numero bigint not null default 0 check (ultimo_numero >= 0),
    updated_at timestamptz not null default now(),
    primary key (empresa_id, cargo_id),
    constraint matriculas_sequencias_cargo_fk
        foreign key (empresa_id, cargo_id)
        references public.cargos (empresa_id, id) on delete restrict
);

commit;
