"""Unidades pertencentes à empresa do administrador autenticado."""
from uuid import UUID
import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, g, jsonify, render_template, request
from db import conectar_bd
from services.unit_onboarding import UnitValidationError, create_unit_with_team, validate_unit_payload
from utils.auth_decorator import require_roles

units_bp = Blueprint('units', __name__)


@units_bp.get('/admin/unidades')
@require_roles('administrador')
def units_page():
    return render_template('unidades.html')


@units_bp.get('/api/admin/unidades')
@require_roles('administrador')
def list_units():
    if request.args:
        return jsonify(erro='A listagem usa somente a empresa da sessão.'), 400
    connection = None
    try:
        company_id = str(UUID(str(g.auth_context['empresa_id'])))
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT id,nome,codigo,timezone,status,endereco_geocodificado,
                          marcacao_mobile_ativa FROM unidades WHERE empresa_id=%s
                   ORDER BY nome,id""", (company_id,),
            )
            units = [dict(row, id=str(row['id'])) for row in cursor.fetchall()]
        return jsonify(unidades=units), 200
    except Exception:
        current_app.logger.error('Falha técnica ao listar unidades.')
        return jsonify(erro='Não foi possível carregar as unidades. Tente novamente.'), 500
    finally:
        if connection:
            connection.close()


@units_bp.post('/api/admin/unidades')
@require_roles('administrador')
def create_unit():
    connection = None
    try:
        if request.args:
            raise ValueError('A criação usa somente a empresa da sessão.')
        data = validate_unit_payload(request.get_json(silent=True))
        company_id = str(UUID(str(g.auth_context['empresa_id'])))
        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            result = create_unit_with_team(cursor, company_id=company_id,
                                          actor_id=g.auth_context['user_id'], data=data)
        connection.commit()
        return jsonify(result), 201
    except UnitValidationError as exc:
        return jsonify(erro=str(exc), campos=exc.fields), 400
    except ValueError as exc:
        if connection:
            connection.rollback()
        return jsonify(erro=str(exc)), 400
    except psycopg2.errors.UniqueViolation as exc:
        if connection:
            connection.rollback()
        keys = {'unidades_empresa_codigo_unique':'codigo', 'unidades_empresa_nome_unique':'nome'}
        key = keys.get(exc.diag.constraint_name)
        if not key:
            return jsonify(erro='Conflito ao criar a unidade. Atualize a lista antes de tentar novamente.'), 409
        message = 'Já existe uma unidade com este código nesta empresa.' if key == 'codigo' else 'Já existe uma unidade com este nome nesta empresa.'
        return jsonify(erro=message, campos={key:message}), 409
    except Exception:
        if connection:
            connection.rollback()
        current_app.logger.error('Falha técnica ao criar unidade; transação abortada.')
        return jsonify(erro='Não foi possível confirmar a criação. Atualize a lista antes de tentar novamente.'), 500
    finally:
        if connection:
            connection.close()
