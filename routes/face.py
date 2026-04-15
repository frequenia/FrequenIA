from flask import Blueprint, request, jsonify
from db import conectar_bd
import cloudinary
import cloudinary.uploader
from deepface import DeepFace
import base64
import os
import shutil
import numpy as np
import cv2
from datetime import datetime
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

load_dotenv()

face_bp = Blueprint("face", __name__)

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("CLOUD_KEY"),
    api_secret=os.getenv("CLOUD_SECRET"),
)

MODEL_NAME = "Facenet"
DETECTOR_CADASTRO = "opencv"
DETECTOR_RECONHECIMENTO = "opencv"

LIMITE_FOTOS = 5
LIMIAR_RECONHECIMENTO = 0.84
CONFIANCA_MINIMA = 0.30
MARGEM_MINIMA = 0.04
PASTA_TEMP = "temp_cadastros"
INTERVALO_MINIMO_PRESENCA_SEGUNDOS = 60

print("Carregando modelo...")
DeepFace.build_model(MODEL_NAME)
print("Modelo carregado!")


# =========================
# FUNÇÕES AUXILIARES
# =========================
def decodificar_base64(imagem_base64):
    if not imagem_base64:
        return None

    if "," in imagem_base64:
        imagem_base64 = imagem_base64.split(",")[1]

    try:
        nparr = np.frombuffer(base64.b64decode(imagem_base64), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def garantir_pasta_temp():
    os.makedirs(PASTA_TEMP, exist_ok=True)


def pasta_usuario(nome):
    return os.path.join(PASTA_TEMP, str(nome))


def limpar_pasta(caminho):
    if os.path.exists(caminho):
        shutil.rmtree(caminho, ignore_errors=True)


def imagem_nitida(img, limite=40):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variancia = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variancia >= limite


def detectar_rosto_unico(img, detector, align=True):
    faces = DeepFace.extract_faces(
        img_path=img, detector_backend=detector, enforce_detection=True, align=align
    )

    if len(faces) != 1:
        return None, "A imagem deve conter exatamente 1 rosto."

    face = faces[0]

    if face.get("confidence", 0) < CONFIANCA_MINIMA:
        return None, "Rosto com baixa confiança."

    face_img = face["face"]

    if face_img.dtype != np.uint8:
        face_img = (face_img * 255).astype(np.uint8)

    return face_img, None


def gerar_embedding(face_img):
    rep = DeepFace.represent(
        img_path=face_img,
        model_name=MODEL_NAME,
        detector_backend="skip",
        enforce_detection=False,
    )

    embedding = np.array(rep[0]["embedding"], dtype=np.float32)
    norma = np.linalg.norm(embedding)

    if norma == 0:
        raise ValueError("Não foi possível normalizar o embedding.")

    embedding = embedding / norma
    return embedding.tolist()


def pode_registrar_presenca(cursor, usuario_id, agora):
    cursor.execute(
        """
        SELECT data_registro, horario_registro
        FROM ponto
        WHERE usuario_id = %s
        ORDER BY data_registro DESC NULLS LAST, horario_registro DESC NULLS LAST
        LIMIT 1
    """,
        (usuario_id,),
    )

    ultima = cursor.fetchone()

    if not ultima:
        return True

    data_ultima = ultima[0]
    hora_ultima = ultima[1]

    if data_ultima is None or hora_ultima is None:
        return True

    dt_ultima = datetime.combine(data_ultima, hora_ultima)
    diferenca = (agora - dt_ultima).total_seconds()

    return diferenca >= INTERVALO_MINIMO_PRESENCA_SEGUNDOS


def reconhecer_uma_imagem(cursor, imagem_base64):
    img = decodificar_base64(imagem_base64)
    if img is None:
        return None

    face_img, erro = detectar_rosto_unico(img, DETECTOR_RECONHECIMENTO, align=True)

    if erro or face_img is None:
        return None

    embedding_input = gerar_embedding(face_img)

    cursor.execute(
        """
        SELECT nome, embedding <-> %s::vector AS distancia
        FROM fotos
        ORDER BY distancia
        LIMIT 5
        """,
        (embedding_input,),
    )

    resultados = cursor.fetchall()

    if not resultados:
        return None

    resultados_ordenados = [(nome, float(distancia)) for nome, distancia in resultados]
    resultados_ordenados.sort(key=lambda x: x[1])

    nome1, dist1 = resultados_ordenados[0]

    # pegar o segundo MELHOR NOME DIFERENTE
    nome2, dist2 = None, 999.0

    for nome, distancia in resultados_ordenados[1:]:
        if nome != nome1:
            nome2, dist2 = nome, distancia
            break

    print(f"Top 5 resultados: {resultados_ordenados}")
    print(f"1º: {nome1} ({dist1}) | 2º: {nome2} ({dist2})")

    if dist1 <= LIMIAR_RECONHECIMENTO and (dist2 - dist1) >= MARGEM_MINIMA:
        return {
            "nome": nome1,
            "distancia": dist1,
            "segundo_nome": nome2,
            "segunda_distancia": dist2,
            "valido": True,
        }

    return {
        "nome": nome1,
        "distancia": dist1,
        "segundo_nome": nome2,
        "segunda_distancia": dist2,
        "valido": False,
    }


# =========================
# CADASTRO - INICIAR
# =========================
@face_bp.route("/iniciar_cadastro", methods=["POST"])
def iniciar_cadastro():
    try:
        dados = request.get_json()
        nome = dados.get("nome")

        if not nome:
            return jsonify({"erro": "Nome inválido!"}), 400

        nome = nome.strip()

        garantir_pasta_temp()
        pasta = pasta_usuario(nome)

        limpar_pasta(pasta)
        os.makedirs(pasta, exist_ok=True)

        return (
            jsonify({"mensagem": "Cadastro iniciado com sucesso.", "nome": nome}),
            200,
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =========================
# CADASTRO - ADICIONAR FOTO
# =========================
@face_bp.route("/adicionar_foto", methods=["POST"])
def adicionar_foto():
    try:
        dados = request.get_json()
        nome = dados.get("nome")
        imagem = dados.get("imagem")

        if not nome or not imagem:
            return jsonify({"erro": "Dados inválidos!"}), 400

        nome = nome.strip()
        pasta = pasta_usuario(nome)

        if not os.path.exists(pasta):
            return jsonify({"erro": "Cadastro não iniciado."}), 400

        arquivos = sorted(
            [
                arq
                for arq in os.listdir(pasta)
                if arq.lower().endswith(".jpg") and not arq.startswith("face_")
            ]
        )

        total_temp = len(arquivos)

        if total_temp >= LIMITE_FOTOS:
            return jsonify({"erro": f"Limite de {LIMITE_FOTOS} fotos atingido!"}), 400

        img = decodificar_base64(imagem)
        if img is None:
            return jsonify({"erro": "Erro ao ler imagem"}), 400

        if not imagem_nitida(img):
            return jsonify({"erro": "Foto borrada. Tente novamente."}), 400

        numero = total_temp + 1
        caminho = os.path.join(pasta, f"{numero}.jpg")
        cv2.imwrite(caminho, img)

        return (
            jsonify(
                {
                    "mensagem": f"Foto {numero}/{LIMITE_FOTOS} salva temporariamente.",
                    "quantidade": numero,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =========================
# CADASTRO - FINALIZAR
# =========================
@face_bp.route("/finalizar_cadastro", methods=["POST"])
def finalizar_cadastro():
    try:
        dados = request.get_json()
        nome = dados.get("nome")

        if not nome:
            return jsonify({"erro": "Nome inválido!"}), 400

        nome = nome.strip()
        pasta = pasta_usuario(nome)

        if not os.path.exists(pasta):
            return jsonify({"erro": "Cadastro não iniciado."}), 400

        arquivos = sorted(
            [
                arq
                for arq in os.listdir(pasta)
                if arq.lower().endswith(".jpg") and not arq.startswith("face_")
            ]
        )

        if len(arquivos) == 0:
            return jsonify({"erro": "Nenhuma foto foi capturada."}), 400

        conn = conectar_bd()
        register_vector(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM fotos WHERE nome = %s", (nome,))
        total_banco = cursor.fetchone()[0]

        if total_banco >= LIMITE_FOTOS:
            cursor.close()
            conn.close()
            limpar_pasta(pasta)
            return (
                jsonify(
                    {
                        "erro": f"Limite de {LIMITE_FOTOS} fotos já atingido para essa pessoa."
                    }
                ),
                400,
            )

        salvas = 0
        erros = []

        for arquivo in arquivos:
            if total_banco >= LIMITE_FOTOS:
                erros.append(f"{arquivo}: limite máximo atingido.")
                break

            caminho = os.path.join(pasta, arquivo)
            img = cv2.imread(caminho)

            if img is None:
                erros.append(f"{arquivo}: erro ao ler imagem.")
                continue

            try:
                face_img, erro = detectar_rosto_unico(
                    img, DETECTOR_CADASTRO, align=True
                )

                if erro:
                    erros.append(f"{arquivo}: {erro}")
                    continue

                embedding = gerar_embedding(face_img)

                caminho_face = os.path.join(pasta, f"face_{arquivo}")
                cv2.imwrite(caminho_face, face_img)

                upload = cloudinary.uploader.upload(
                    caminho_face,
                    folder=f"rostos/{nome}",
                    public_id=str(total_banco + 1),
                    overwrite=True,
                )

                url = upload["secure_url"]

                cursor.execute(
                    "INSERT INTO fotos (nome, url, embedding) VALUES (%s, %s, %s)",
                    (nome, url, embedding),
                )

                total_banco += 1
                salvas += 1

                if os.path.exists(caminho_face):
                    os.remove(caminho_face)

            except Exception as e:
                erros.append(f"{arquivo}: {str(e)}")

        conn.commit()
        cursor.close()
        conn.close()

        limpar_pasta(pasta)

        if salvas == 0:
            return (
                jsonify({"erro": "Nenhuma foto válida foi salva.", "erros": erros}),
                400,
            )

        return (
            jsonify(
                {
                    "mensagem": f"{salvas} foto(s) processada(s) com sucesso.",
                    "total_cadastrado": total_banco,
                    "erros": erros,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =========================
# RECONHECIMENTO
@face_bp.route("/reconhecer", methods=["POST"])
def reconhecer():
    try:
        dados = request.get_json()

        imagem = dados.get("imagem")
        imagens = dados.get("imagens")

        lista_imagens = []

        if imagens and isinstance(imagens, list):
            lista_imagens = [img for img in imagens if img]
        elif imagem:
            lista_imagens = [imagem]
        else:
            return (
                jsonify({"erro": "Envie 'imagem' ou 'imagens' para reconhecimento."}),
                400,
            )

        conn = conectar_bd()
        register_vector(conn)
        cursor = conn.cursor()

        resultados_validos = []
        resultados_invalidos = []

        for img_base64 in lista_imagens:
            resultado = reconhecer_uma_imagem(cursor, img_base64)
            if not resultado:
                continue

            if resultado["valido"]:
                resultados_validos.append(resultado)
            else:
                resultados_invalidos.append(resultado)

        if not resultados_validos:
            melhor_tentativa = None

            if resultados_invalidos:
                melhor_tentativa = min(resultados_invalidos, key=lambda x: x["distancia"])

            cursor.close()
            conn.close()

            if melhor_tentativa:
                return (
                    jsonify(
                        {
                            "erro": "Não reconhecido",
                            "nome_mais_proximo": melhor_tentativa["nome"],
                            "distancia": melhor_tentativa["distancia"],
                            "segundo_nome": melhor_tentativa["segundo_nome"],
                            "segunda_distancia": melhor_tentativa["segunda_distancia"],
                        }
                    ),
                    404,
                )

            return jsonify({"erro": "Nenhum rosto válido detectado"}), 404

        contagem = {}
        distancias = {}

        for r in resultados_validos:
            nome = r["nome"]
            distancia = r["distancia"]

            contagem[nome] = contagem.get(nome, 0) + 1
            distancias.setdefault(nome, []).append(distancia)

        nome_final = max(contagem, key=contagem.get)
        cursor.execute("""
        SELECT u.id
        FROM usuarios u
        INNER JOIN fotos f ON u.nome = f.nome
        WHERE f.nome = %s
        LIMIT 1
        """, (nome_final,))

        usuario = cursor.fetchone()

        if not usuario:
            cursor.close()
            conn.close()
            return jsonify({"erro": "Usuário não encontrado"}), 404

        usuario_id = usuario[0]
        distancias_nome = distancias[nome_final]
        melhor_distancia_final = min(distancias_nome)
        media_distancia = sum(distancias_nome) / len(distancias_nome)

        print("Resultados válidos:", resultados_validos)
        print("Nome final:", nome_final)
        print("Melhor distância:", melhor_distancia_final)
        print("Média distância:", media_distancia)

        agora = datetime.now()

        if pode_registrar_presenca(cursor, nome_final, agora):
            cursor.execute(
                """
                INSERT INTO ponto (usuario_id, data_registro, horario_registro)
                VALUES (%s, %s, %s)
                """,
                (nome_final, agora.date(), agora.time().replace(microsecond=0)),
            )
            conn.commit()

        cursor.close()
        conn.close()

        return (
            jsonify(
                {
                    "nome": nome_final,
                    "distancia": melhor_distancia_final,
                    "media_distancia": media_distancia,
                    "data": agora.strftime("%d/%m/%Y"),
                    "horario": agora.strftime("%H:%M:%S"),
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500