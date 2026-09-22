begin;

alter table public.correcoes
    add column if not exists ocorrencia_id uuid;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'correcoes_ocorrencia_fk'
    ) then
        alter table public.correcoes
            add constraint correcoes_ocorrencia_fk
            foreign key (ocorrencia_id) references public.ocorrencias(id) on delete restrict;
    end if;
end
$$;

create unique index if not exists correcoes_ocorrencia_unique
    on public.correcoes (ocorrencia_id)
    where ocorrencia_id is not null;

commit;
