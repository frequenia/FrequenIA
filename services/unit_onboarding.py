"""Criação atômica da unidade, equipe inicial e auditoria."""
import re
import psycopg2.extras
from utils.schedules import validate_timezone


class UnitValidationError(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__('Confira os campos destacados antes de salvar.')


def validate_unit_payload(payload):
    allowed = {'nome', 'codigo', 'timezone', 'equipe_nome'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('A requisição contém campos não permitidos.')
    fields, data = {}, {}
    for key, label, default in [('nome', 'nome da unidade', ''), ('equipe_nome', 'nome da primeira equipe', 'Geral')]:
        value = payload.get(key, default)
        value = ' '.join(value.split()) if isinstance(value, str) else ''
        if not 1 <= len(value) <= 160 or '\x00' in value:
            fields[key] = f'Informe o {label}, com até 160 caracteres.'
        data[key] = value
    code = payload.get('codigo')
    code = code.strip().upper() if isinstance(code, str) else ''
    if not re.fullmatch(r'[A-Z0-9_-]{1,40}', code):
        fields['codigo'] = 'Use até 40 caracteres: letras sem acento, números, hífen ou sublinhado.'
    data['codigo'] = code
    timezone = payload.get('timezone', 'America/Sao_Paulo')
    try:
        if not isinstance(timezone, str) or not timezone.strip() or len(timezone) > 100:
            raise ValueError
        data['timezone'] = validate_timezone(timezone)
    except ValueError:
        fields['timezone'] = 'Informe um fuso válido, como America/Sao_Paulo.'
    if fields:
        raise UnitValidationError(fields)
    return data


def create_unit_with_team(cursor, *, company_id, actor_id, data):
    cursor.execute(
        """INSERT INTO unidades (empresa_id,nome,codigo,timezone,status,marcacao_mobile_ativa)
           VALUES (%s,%s,%s,%s,'ativa',false)
           RETURNING id,nome,codigo,timezone,status,marcacao_mobile_ativa""",
        (company_id, data['nome'], data['codigo'], data['timezone']),
    )
    unit = cursor.fetchone()
    cursor.execute(
        """INSERT INTO equipes (empresa_id,unidade_id,nome,status)
           VALUES (%s,%s,%s,'ativa') RETURNING id,nome""",
        (company_id, unit['id'], data['equipe_nome']),
    )
    team = cursor.fetchone()
    for action, entity, identifier, metadata in [
        ('unidade.criada', 'unidade', unit['id'], {'codigo':unit['codigo'], 'timezone':unit['timezone']}),
        ('equipe.criada', 'equipe', team['id'], {'unidade_id':str(unit['id'])}),
    ]:
        cursor.execute(
            """INSERT INTO auditoria (empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,metadados)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (company_id, actor_id, action, entity, identifier, psycopg2.extras.Json(metadata)),
        )
    return {'unidade':dict(unit, id=str(unit['id'])), 'equipe':dict(team, id=str(team['id']))}
