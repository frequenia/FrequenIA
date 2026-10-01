"""Autenticação de terminais de ponto provisionados por empresa."""

from functools import wraps
from uuid import UUID

from flask import g, jsonify, redirect, session, url_for

from db import conectar_bd


def terminal_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        terminal_id = session.get("terminal_ponto_id")
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
        return view(*args, **kwargs)

    return wrapped
