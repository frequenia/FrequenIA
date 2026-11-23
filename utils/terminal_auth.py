"""Autenticação de terminais de ponto provisionados por empresa."""

from functools import wraps
from uuid import UUID

from flask import current_app, g, jsonify, redirect, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from db import conectar_bd

TERMINAL_COOKIE = 'frequenia_terminal'
# Prazo de retenção do navegador, renovado a cada uso; não é uma expiração
# da autorização do terminal. Navegadores podem limitar/apagar cookies.
TERMINAL_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def _signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='frequenia-terminal-v1')


def terminal_browser_id():
    """Cookie dedicado não é apagado pelo login/logout de uma pessoa."""
    signed = request.cookies.get(TERMINAL_COOKIE)
    if signed:
        try:
            value = _signer().loads(signed)
        except BadSignature:
            return None
    else:
        value = session.get('terminal_ponto_id')  # compatibilidade de ativação antiga
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def remember_terminal(response, terminal_id):
    response.set_cookie(TERMINAL_COOKIE, _signer().dumps(str(UUID(str(terminal_id)))),
                        max_age=TERMINAL_COOKIE_MAX_AGE, httponly=True,
                        secure=current_app.config.get('SESSION_COOKIE_SECURE', False),
                        samesite='Strict', path='/')
    return response


def forget_terminal(response):
    response.delete_cookie(TERMINAL_COOKIE, path='/', httponly=True,
                           secure=current_app.config.get('SESSION_COOKIE_SECURE', False), samesite='Strict')
    return response


def terminal_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        terminal_id = terminal_browser_id()
        try:
            terminal_id = str(UUID(str(terminal_id)))
        except (TypeError, ValueError, AttributeError):
            session.pop("terminal_ponto_id", None)
            if view.__name__ in {"kiosk_page", "reconhecimento_facial"}:
                return redirect(url_for("kiosk.activation_page"))
            return jsonify({"erro": "Terminal não autenticado."}), 401

        connection = conectar_bd()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id, empresa_id FROM terminais_ponto
                       WHERE id = %s AND status = 'ativo' AND revoked_at IS NULL""",
                    (terminal_id,),
                )
                terminal = cursor.fetchone()
        finally:
            connection.close()
        if not terminal:
            session.pop("terminal_ponto_id", None)
            if view.__name__ in {"kiosk_page", "reconhecimento_facial"}:
                return redirect(url_for("kiosk.activation_page"))
            return jsonify({"erro": "Terminal não autenticado."}), 401
        g.terminal_context = {"terminal_id": str(terminal[0]), "empresa_id": str(terminal[1])}
        response = current_app.make_response(view(*args, **kwargs))
        # Renova apenas após validar no banco; revogação continua imediata.
        remember_terminal(response, terminal_id)
        return response

    return wrapped
