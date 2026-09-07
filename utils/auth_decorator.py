from functools import wraps

import jwt
from flask import current_app, g, jsonify, redirect, request, session, url_for

from db import buscar_sessao_access


JWT_ALGORITHM = "HS256"


def _unauthorized(message="Autenticação necessária."):
    return jsonify({"erro": message}), 401


def _load_persistent_authentication():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if authorization:
        if scheme.lower() != "bearer" or not separator or not token.strip():
            return None, _unauthorized("Token de acesso inválido.")

        try:
            payload = jwt.decode(
                token.strip(),
                current_app.config["JWT_SECRET_KEY"],
                algorithms=[JWT_ALGORITHM],
                options={
                    "require": ["sub", "funcionario_id", "sid", "iat", "exp"]
                },
            )
        except jwt.ExpiredSignatureError:
            return None, _unauthorized("Token de acesso expirado.")
        except jwt.InvalidTokenError:
            return None, _unauthorized("Token de acesso inválido.")

        if payload.get("type") != "access":
            return None, _unauthorized("Token de acesso inválido.")

        auth_session = buscar_sessao_access(
            payload["sid"],
            payload["sub"],
            payload["funcionario_id"],
        )
        if not auth_session:
            return None, _unauthorized("Token de acesso inválido.")

        context = {
            "user_id": str(payload["sub"]),
            "funcionario_id": str(payload["funcionario_id"]),
            "session_id": str(payload["sid"]),
            "familia_id": str(auth_session["familia_id"]),
            "empresa_id": str(auth_session["empresa_id"]),
            "perfil": auth_session["perfil"],
        }
        return context, None

    required_session_fields = (
        "user_id",
        "funcionario_id",
        "auth_session_id",
    )
    if not all(session.get(field) for field in required_session_fields):
        return None, _unauthorized()

    auth_session = buscar_sessao_access(
        session["auth_session_id"],
        session["user_id"],
        session["funcionario_id"],
    )
    if not auth_session:
        session.clear()
        return None, _unauthorized("Sessão inválida ou revogada.")

    context = {
        "user_id": str(auth_session["user_id"]),
        "funcionario_id": str(auth_session["funcionario_id"]),
        "session_id": str(auth_session["session_id"]),
        "familia_id": str(auth_session["familia_id"]),
        "empresa_id": str(auth_session["empresa_id"]),
        "perfil": auth_session["perfil"],
    }
    return context, None


def _set_auth_context(context):
    g.auth_user_id = context["user_id"]
    g.auth_funcionario_id = context["funcionario_id"]
    g.auth_session_id = context["session_id"]
    g.auth_session_family_id = context["familia_id"]
    g.auth_context = context


def access_token_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token.strip():
            return _unauthorized("Token de acesso ausente.")

        context, error_response = _load_persistent_authentication()
        if error_response:
            return error_response

        _set_auth_context(context)
        return view_function(*args, **kwargs)

    return decorated_function


def require_roles(*allowed_roles):
    allowed = frozenset(allowed_roles)

    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            context, error_response = _load_persistent_authentication()
            if error_response:
                return error_response

            _set_auth_context(context)
            if context["perfil"] not in allowed:
                return jsonify({"erro": "Acesso não autorizado."}), 403

            return view_function(*args, **kwargs)

        return decorated_function

    return decorator

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("views.login_page"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    return require_roles("administrador")(f)
