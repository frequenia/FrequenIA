begin;

create table public.politicas_biometricas (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    finalidade text not null,
    versao text not null,
    referencia_base_legal text not null,
    versao_aviso text not null,
    referencia_documental text not null,
    canal_atendimento text not null,
    retencao_dias integer,
    estado text not null default 'rascunho'
        check (estado in ('rascunho', 'aprovada', 'encerrada')),
    vigencia_inicio timestamptz not null,
    vigencia_fim timestamptz,
    aprovado_por_usuario_id uuid,
    aprovado_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    constraint politicas_biometricas_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint politicas_biometricas_aprovador_fk
        foreign key (aprovado_por_usuario_id) references public.usuarios(id) on delete restrict,
    constraint politicas_biometricas_empresa_id_unique unique (empresa_id, id),
    constraint politicas_biometricas_versao_unique unique (empresa_id, finalidade, versao),
    check (finalidade ~ '^[a-z0-9_.-]{1,80}$'),
    check (versao = btrim(versao) and versao <> '' and length(versao) <= 80),
    check (referencia_base_legal = btrim(referencia_base_legal) and referencia_base_legal <> '' and length(referencia_base_legal) <= 240),
    check (versao_aviso = btrim(versao_aviso) and versao_aviso <> '' and length(versao_aviso) <= 80),
    check (referencia_documental = btrim(referencia_documental) and referencia_documental <> '' and length(referencia_documental) <= 240),
    check (canal_atendimento = btrim(canal_atendimento) and canal_atendimento <> '' and length(canal_atendimento) <= 240),
    check (retencao_dias is null or retencao_dias between 1 and 36500),
    check (vigencia_fim is null or vigencia_fim > vigencia_inicio),
    check (
        (estado = 'aprovada' and aprovado_por_usuario_id is not null
         and aprovado_at is not null and retencao_dias is not null)
        or estado <> 'aprovada'
    )
);

create index politicas_biometricas_resolucao_idx
    on public.politicas_biometricas (empresa_id, finalidade, vigencia_inicio desc)
    where estado = 'aprovada';

create or replace function public.validar_politica_biometrica_sem_sobreposicao()
returns trigger language plpgsql as $$
begin
    if new.estado = 'aprovada' and exists (
        select 1 from public.politicas_biometricas p
        where p.empresa_id = new.empresa_id
          and p.finalidade = new.finalidade
          and p.estado = 'aprovada'
          and p.id <> new.id
          and tstzrange(p.vigencia_inicio, p.vigencia_fim, '[)')
              && tstzrange(new.vigencia_inicio, new.vigencia_fim, '[)')
    ) then
        raise exception 'politica_biometrica_sobreposta' using errcode = '23P01';
    end if;
    return new;
end $$;

create trigger politicas_biometricas_sem_sobreposicao
before insert or update on public.politicas_biometricas
for each row execute function public.validar_politica_biometrica_sem_sobreposicao();

create or replace function public.politica_biometrica_append_only()
returns trigger language plpgsql as $$
begin
    if old.estado = 'aprovada' then
        raise exception 'politica_biometrica_aprovada_imutavel' using errcode = '55000';
    end if;
    return new;
end $$;

create trigger politicas_biometricas_append_only
before update or delete on public.politicas_biometricas
for each row execute function public.politica_biometrica_append_only();

create table public.perfis_tecnicos_biometricos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    finalidade text not null,
    versao text not null,
    modelo text not null,
    versao_modelo text not null,
    dimensao integer not null,
    metrica text not null,
    limiar double precision not null,
    versao_liveness text not null,
    referencia_relatorio text not null,
    estado text not null default 'rascunho'
        check (estado in ('rascunho', 'ativo', 'inativo')),
    vigencia_inicio timestamptz not null,
    vigencia_fim timestamptz,
    aprovado_por_usuario_id uuid,
    aprovado_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    constraint perfis_biometricos_empresa_fk
        foreign key (empresa_id) references public.empresas(id) on delete restrict,
    constraint perfis_biometricos_aprovador_fk
        foreign key (aprovado_por_usuario_id) references public.usuarios(id) on delete restrict,
    constraint perfis_biometricos_empresa_id_unique unique (empresa_id, id),
    constraint perfis_biometricos_versao_unique unique (empresa_id, finalidade, versao),
    check (finalidade ~ '^[a-z0-9_.-]{1,80}$'),
    check (modelo = btrim(modelo) and modelo <> '' and length(modelo) <= 80),
    check (versao_modelo = btrim(versao_modelo) and versao_modelo <> '' and length(versao_modelo) <= 120),
    check (dimensao between 1 and 4096),
    check (metrica in ('cosine_distance')),
    check (limiar > 0 and limiar <= 2),
    check (versao_liveness = btrim(versao_liveness) and versao_liveness <> '' and length(versao_liveness) <= 120),
    check (referencia_relatorio = btrim(referencia_relatorio) and referencia_relatorio <> '' and length(referencia_relatorio) <= 240),
    check (vigencia_fim is null or vigencia_fim > vigencia_inicio),
    check ((estado = 'ativo' and aprovado_por_usuario_id is not null and aprovado_at is not null) or estado <> 'ativo')
);

create unique index perfis_biometricos_um_ativo_idx
    on public.perfis_tecnicos_biometricos (empresa_id, finalidade)
    where estado = 'ativo' and vigencia_fim is null;

alter table public.biometrias
    drop constraint if exists biometrias_status_check;
alter table public.biometrias
    alter column embedding drop not null,
    add constraint biometrias_empresa_id_unique unique (empresa_id, id),
    add column politica_biometrica_id uuid,
    add column perfil_tecnico_id uuid,
    add column motivo_codigo text,
    add column bloqueada_at timestamptz,
    add column exclusao_solicitada_at timestamptz,
    add column eliminada_at timestamptz,
    add column eliminacao_elegivel_at timestamptz,
    add constraint biometrias_status_check
        check (status in ('ativa', 'bloqueada', 'revogada', 'exclusao_pendente', 'eliminada')),
    add constraint biometrias_politica_fk
        foreign key (empresa_id, politica_biometrica_id)
        references public.politicas_biometricas (empresa_id, id) on delete restrict,
    add constraint biometrias_perfil_fk
        foreign key (empresa_id, perfil_tecnico_id)
        references public.perfis_tecnicos_biometricos (empresa_id, id) on delete restrict,
    add constraint biometrias_material_estado_check check (
        (status = 'eliminada' and embedding is null
         and referencia_arquivo_privado is null and eliminada_at is not null)
        or
        (status <> 'eliminada' and embedding is not null and eliminada_at is null)
    ),
    add constraint biometrias_motivo_check check (
        motivo_codigo is null or motivo_codigo ~ '^[a-z0-9_.-]{1,100}$'
    ),
    add constraint biometrias_exclusao_check check (
        (status = 'exclusao_pendente' and exclusao_solicitada_at is not null)
        or status <> 'exclusao_pendente'
    );

create index biometrias_governanca_idx
    on public.biometrias (empresa_id, funcionario_id, status, eliminacao_elegivel_at);
create unique index biometrias_uma_ativa_por_vinculo_idx
    on public.biometrias (empresa_id, funcionario_id)
    where status = 'ativa';

create table public.holds_biometricos (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    biometria_id uuid not null,
    versao integer not null default 1 check (versao > 0),
    justificativa text not null,
    referencia text not null,
    criado_por_usuario_id uuid not null,
    created_at timestamptz not null default clock_timestamp(),
    expira_at timestamptz,
    cancelado_at timestamptz,
    cancelado_por_usuario_id uuid,
    motivo_cancelamento text,
    constraint holds_biometricos_biometria_fk
        foreign key (empresa_id, biometria_id) references public.biometrias(empresa_id, id) on delete restrict,
    constraint holds_biometricos_criador_fk
        foreign key (criado_por_usuario_id) references public.usuarios(id) on delete restrict,
    constraint holds_biometricos_cancelador_fk
        foreign key (cancelado_por_usuario_id) references public.usuarios(id) on delete restrict,
    constraint holds_biometricos_versao_unique unique (empresa_id, biometria_id, versao),
    check (justificativa = btrim(justificativa) and justificativa <> '' and length(justificativa) <= 500),
    check (referencia = btrim(referencia) and referencia <> '' and length(referencia) <= 240),
    check (expira_at is null or expira_at > created_at),
    check ((cancelado_at is null and cancelado_por_usuario_id is null and motivo_cancelamento is null)
        or (cancelado_at is not null and cancelado_por_usuario_id is not null
            and motivo_cancelamento = btrim(motivo_cancelamento) and motivo_cancelamento <> ''))
);

create unique index holds_biometricos_ativo_idx
    on public.holds_biometricos (empresa_id, biometria_id)
    where cancelado_at is null;

create table public.operacoes_biometricas (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    biometria_id uuid,
    funcionario_id uuid not null,
    chave_idempotencia text not null,
    operacao text not null,
    motivo_codigo text not null,
    ator_usuario_id uuid not null,
    estado_resultante text not null,
    created_at timestamptz not null default clock_timestamp(),
    constraint operacoes_biometricas_funcionario_fk
        foreign key (empresa_id, funcionario_id) references public.funcionarios(empresa_id, id) on delete restrict,
    constraint operacoes_biometricas_biometria_fk
        foreign key (empresa_id, biometria_id) references public.biometrias(empresa_id, id) on delete restrict,
    constraint operacoes_biometricas_ator_fk
        foreign key (ator_usuario_id) references public.usuarios(id) on delete restrict,
    constraint operacoes_biometricas_idempotencia_unique unique (empresa_id, chave_idempotencia),
    check (length(chave_idempotencia) between 8 and 200),
    check (operacao in ('bloquear', 'revogar', 'solicitar_exclusao', 'criar_hold', 'cancelar_hold')),
    check (motivo_codigo ~ '^[a-z0-9_.-]{1,100}$')
);

create table public.historico_ciclo_biometrico (
    id uuid primary key default extensions.gen_random_uuid(),
    empresa_id uuid not null,
    biometria_id uuid not null,
    funcionario_id uuid not null,
    ator_usuario_id uuid,
    acao text not null,
    estado_anterior text,
    estado_novo text not null,
    motivo_codigo text not null,
    politica_biometrica_id uuid,
    perfil_tecnico_id uuid,
    ocorrido_at timestamptz not null default clock_timestamp(),
    constraint historico_ciclo_biometria_fk
        foreign key (empresa_id, biometria_id) references public.biometrias(empresa_id, id) on delete restrict,
    constraint historico_ciclo_funcionario_fk
        foreign key (empresa_id, funcionario_id) references public.funcionarios(empresa_id, id) on delete restrict,
    constraint historico_ciclo_ator_fk
        foreign key (ator_usuario_id) references public.usuarios(id) on delete restrict,
    check (acao ~ '^[a-z0-9_.-]{1,100}$'),
    check (motivo_codigo ~ '^[a-z0-9_.-]{1,100}$')
);

create index historico_ciclo_biometria_idx
    on public.historico_ciclo_biometrico (empresa_id, biometria_id, ocorrido_at, id);

create or replace function public.historico_biometrico_append_only()
returns trigger language plpgsql as $$
begin
    raise exception 'historico_biometrico_append_only' using errcode = '55000';
end $$;
create trigger historico_biometrico_append_only
before update or delete on public.historico_ciclo_biometrico
for each row execute function public.historico_biometrico_append_only();

create or replace function public.auditoria_metadados_seguros(value jsonb)
returns boolean language plpgsql immutable parallel safe as $$
declare
    item record;
    child jsonb;
begin
    if jsonb_typeof(value) = 'object' then
        for item in select key, val from jsonb_each(value) as e(key, val) loop
            if lower(item.key) = any (array[
                'senha','password','token','refresh_token','embedding','embeddings',
                'foto','fotos','imagem','imagens','score','distancia_facial','hash',
                'cpf','matricula','caminho','path','secret','segredo','referencia_arquivo_privado'
            ]) then
                return false;
            end if;
            if not public.auditoria_metadados_seguros(item.val) then
                return false;
            end if;
        end loop;
    elsif jsonb_typeof(value) = 'array' then
        for child in select element from jsonb_array_elements(value) as a(element) loop
            if not public.auditoria_metadados_seguros(child) then
                return false;
            end if;
        end loop;
    end if;
    return true;
end;
$$;

create or replace function public.validar_auditoria_metadados_seguros()
returns trigger language plpgsql as $$
begin
    if not public.auditoria_metadados_seguros(new.metadados) then
        raise exception 'auditoria_metadados_sensiveis' using errcode = '22023';
    end if;
    return new;
end $$;

create trigger auditoria_metadados_seguros
before insert or update of metadados on public.auditoria
for each row execute function public.validar_auditoria_metadados_seguros();

commit;
