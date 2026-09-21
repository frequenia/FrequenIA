"""Compatibilidade para URLs faciais legadas, definitivamente desativadas.

O cadastro oficial usa ``routes.biometrics`` com empresa/funcionário validados.
Nenhuma rota deste blueprint recebe imagem, acessa arquivos ou consulta o banco.
"""

from flask import Blueprint, jsonify


face_bp = Blueprint("face", __name__)


def _legacy_face_gone():
    return jsonify({"erro": "Fluxo facial legado desativado. Utilize a API biométrica oficial."}), 410


face_bp.add_url_rule("/iniciar_cadastro", "iniciar_cadastro", _legacy_face_gone, methods=["POST"])
face_bp.add_url_rule("/adicionar_foto", "adicionar_foto", _legacy_face_gone, methods=["POST"])
face_bp.add_url_rule("/finalizar_cadastro", "finalizar_cadastro", _legacy_face_gone, methods=["POST"])
face_bp.add_url_rule("/reconhecer", "reconhecer", _legacy_face_gone, methods=["POST"])
face_bp.add_url_rule("/confirmar_ponto", "confirmar_ponto", _legacy_face_gone, methods=["POST"])
