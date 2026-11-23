"""Acesso somente ao avatar da própria conta autenticada."""
from hmac import compare_digest
from uuid import UUID
from flask import Blueprint, Response, current_app, g, jsonify, request, session
from db import conectar_bd
from utils.auth_decorator import require_roles
from services.profile_photo import MAX_UPLOAD_BYTES, normalize_profile_photo

profile_photo_bp = Blueprint('profile_photo', __name__)
ROLES = ('administrador', 'funcionario', 'gestor', 'rh')


@profile_photo_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@profile_photo_bp.route('/api/perfil/foto', methods=['GET', 'PUT', 'DELETE'])
@require_roles(*ROLES)
def own_photo():
    connection = None
    try:
        if request.args:
            return jsonify(erro='A foto pertence somente à conta conectada.'), 400
        if request.method != 'GET':
            expected = session.get('profile_photo_csrf', '')
            supplied = request.headers.get('X-Profile-Token', '')
            if not expected or not compare_digest(expected, supplied):
                return jsonify(erro='Atualize a página antes de alterar sua foto.'), 403
        user_id = str(UUID(g.auth_context['user_id']))
        content = None
        if request.method == 'PUT':
            # Raw body: avoids multipart filenames, disk spooling and unlimited reads.
            if request.content_length and request.content_length > MAX_UPLOAD_BYTES:
                return jsonify(erro='A imagem deve ter até 5 MB.'), 413
            content = request.stream.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                return jsonify(erro='A imagem deve ter até 5 MB.'), 413
            content = normalize_profile_photo(content)
        connection = conectar_bd()
        with connection.cursor() as cursor:
            if request.method == 'GET':
                cursor.execute('SELECT conteudo FROM fotos_perfil WHERE usuario_id=%s', (user_id,))
                row = cursor.fetchone()
                if not row:
                    return Response(status=204)
                return Response(bytes(row[0]), mimetype='image/jpeg')
            if request.method == 'PUT':
                cursor.execute('''INSERT INTO fotos_perfil (usuario_id,conteudo) VALUES (%s,%s)
                    ON CONFLICT (usuario_id) DO UPDATE SET conteudo=EXCLUDED.conteudo,
                    updated_at=clock_timestamp()''', (user_id, content))
            else:
                cursor.execute('DELETE FROM fotos_perfil WHERE usuario_id=%s', (user_id,))
        connection.commit()
        return jsonify(mensagem='Foto atualizada.' if content else 'Foto removida.'), 200
    except ValueError as exc:
        return jsonify(erro=str(exc)), 400
    except Exception:
        if connection:
            connection.rollback()
        current_app.logger.error('Falha técnica no avatar da conta; nenhum conteúdo registrado.')
        return jsonify(erro='Não foi possível acessar a foto agora. Tente novamente.'), 503
    finally:
        if connection:
            connection.close()
