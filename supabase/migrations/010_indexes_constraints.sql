begin;

-- UNIQUE constraints already index usuarios.cpf, usuarios.email and
-- auth_sessions.refresh_token_hash. No duplicate indexes are created here.

create index unidades_empresa_idx
    on public.unidades (empresa_id);
create index equipes_empresa_unidade_idx
    on public.equipes (empresa_id, unidade_id);
create index cargos_empresa_idx
    on public.cargos (empresa_id);

create index funcionarios_usuario_idx
    on public.funcionarios (usuario_id);
create index funcionarios_empresa_unidade_idx
    on public.funcionarios (empresa_id, unidade_id);
create index funcionarios_empresa_equipe_idx
    on public.funcionarios (empresa_id, equipe_id)
    where equipe_id is not null;
create index funcionarios_empresa_cargo_idx
    on public.funcionarios (empresa_id, cargo_id)
    where cargo_id is not null;

create index turnos_empresa_idx
    on public.turnos (empresa_id);
create index periodos_turno_turno_idx
    on public.periodos_turno (turno_id, dia_semana, ordem);
create index funcionarios_turnos_funcionario_vigencia_idx
    on public.funcionarios_turnos (funcionario_id, vigencia_inicio desc);
create index funcionarios_turnos_turno_idx
    on public.funcionarios_turnos (turno_id);

create index biometrias_funcionario_idx
    on public.biometrias (funcionario_id, status);

create index auth_sessions_usuario_expiracao_idx
    on public.auth_sessions (usuario_id, expires_at desc);
create index auth_sessions_familia_idx
    on public.auth_sessions (familia_id);
create index auth_sessions_ativas_idx
    on public.auth_sessions (usuario_id, expires_at)
    where revoked_at is null;

create index tentativas_faciais_funcionario_instante_idx
    on public.tentativas_faciais (funcionario_id, instante desc);
create index tentativas_faciais_empresa_instante_idx
    on public.tentativas_faciais (empresa_id, instante desc);
create index marcacoes_funcionario_instante_idx
    on public.marcacoes (funcionario_id, instante desc);
create index marcacoes_empresa_instante_idx
    on public.marcacoes (empresa_id, instante desc);

create index ocorrencias_funcionario_estado_idx
    on public.ocorrencias (funcionario_id, estado, created_at desc);
create index ocorrencias_responsavel_idx
    on public.ocorrencias (responsavel_usuario_id)
    where responsavel_usuario_id is not null;
create index correcoes_funcionario_estado_idx
    on public.correcoes (funcionario_id, estado, created_at desc);
create index correcoes_solicitante_idx
    on public.correcoes (solicitante_usuario_id, created_at desc);
create index correcoes_responsavel_decisao_idx
    on public.correcoes (responsavel_decisao_usuario_id)
    where responsavel_decisao_usuario_id is not null;

create index notificacoes_usuario_nao_lidas_idx
    on public.notificacoes (usuario_id, created_at desc)
    where read_at is null;
create index auditoria_empresa_ocorrido_idx
    on public.auditoria (empresa_id, ocorrido_at desc)
    where empresa_id is not null;
create index auditoria_ator_ocorrido_idx
    on public.auditoria (ator_usuario_id, ocorrido_at desc)
    where ator_usuario_id is not null;

-- ANN index intentionally omitted. Facial matching is scoped to the
-- authenticated employee, so a global HNSW/IVFFlat index is unnecessary.

commit;
