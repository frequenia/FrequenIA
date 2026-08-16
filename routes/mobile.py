from flask import Blueprint, jsonify, request
from db import conectar_bd
import psycopg2.extras

mobile_bp = Blueprint("mobile", __name__)


@mobile_bp.route("/mobile/test", methods=["GET"])
def mobile_test():
    return jsonify({
        "ok": True,
        "message": "API do FREQUEN.IA funcionando"
    })


@mobile_bp.route("/mobile/foto", methods=["POST"])
def receber_foto():
    if "foto" not in request.files:
        return jsonify({
            "ok": False,
            "message": "Nenhuma foto foi enviada"
        }), 400

    foto = request.files["foto"]

    print("Foto recebida:", foto.filename)

    return jsonify({
        "ok": True,
        "message": "Foto recebida com sucesso!"
    })


@mobile_bp.route("/mobile/usuarios-sem-fotos", methods=["GET"])
def usuarios_sem_fotos():
    conn = None
    cursor = None

    try:
        conn = conectar_bd()
        cursor = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cursor.execute("""
            SELECT u.id, u.nome
            FROM usuarios u
            LEFT JOIN fotos f ON f.nome = u.nome
            WHERE f.nome IS NULL
            ORDER BY u.nome
        """)

        usuarios = cursor.fetchall()

        return jsonify({
            "ok": True,
            "usuarios": usuarios
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "erro": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()