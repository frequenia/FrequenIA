\set ON_ERROR_STOP on
-- Run only inside a dedicated synthetic database, as owner.
create table public.usuarios (id uuid primary key);
do $$ begin
    if not exists (select 1 from pg_roles where rolname='anon') then create role anon; end if;
    if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
end $$;
\i /tmp/profile-photo-migration.sql
insert into usuarios values ('11111111-1111-4111-8111-111111111111'),('22222222-2222-4222-8222-222222222222');
insert into fotos_perfil (usuario_id,conteudo) values ('11111111-1111-4111-8111-111111111111',decode('010203','hex'));
insert into fotos_perfil (usuario_id,conteudo) values ('11111111-1111-4111-8111-111111111111',decode('040506','hex'))
on conflict (usuario_id) do update set conteudo=excluded.conteudo;
do $$ begin
    if (select count(*) from fotos_perfil) <> 1 then raise exception 'replace_failed'; end if;
    if exists(select 1 from fotos_perfil where usuario_id='22222222-2222-4222-8222-222222222222') then raise exception 'ownership_failed'; end if;
    begin
        insert into fotos_perfil values ('22222222-2222-4222-8222-222222222222',decode(repeat('00',262145),'hex'),now());
        raise exception 'size_not_enforced';
    exception when check_violation then null; end;
    if has_table_privilege('anon','fotos_perfil','SELECT') or has_table_privilege('authenticated','fotos_perfil','SELECT') then raise exception 'public_access'; end if;
    if not (select relrowsecurity from pg_class where oid='fotos_perfil'::regclass) then raise exception 'rls_disabled'; end if;
end $$;
-- RLS continues denying access even if SELECT is granted by mistake later.
grant select on fotos_perfil to authenticated;
set role authenticated;
do $$ begin if exists(select 1 from fotos_perfil) then raise exception 'rls_leak'; end if; end $$;
reset role;
revoke select on fotos_perfil from authenticated;
delete from usuarios where id='11111111-1111-4111-8111-111111111111';
do $$ begin if exists(select 1 from fotos_perfil) then raise exception 'cascade_failed'; end if; end $$;
select 'profile_photo_schema: replace=1; size_limit=1; private=1; rls=1; cascade=1' as result;
