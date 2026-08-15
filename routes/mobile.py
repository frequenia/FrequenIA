from flask import Blueprint, jsonify, request

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