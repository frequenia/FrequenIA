"""Infraestrutura facial compartilhada.

O modulo nao importa DeepFace nem constroi modelos durante o import. O codigo
legado usa este servico enquanto as novas funcionalidades biometricas serao
implementadas separadamente em fases futuras.
"""

import logging
import math
import threading

LOGGER = logging.getLogger(__name__)
MODEL_NAME = "ArcFace"
MODEL_VERSION = "deepface-0.0.99"
EMBEDDING_DIMENSION = 512

_model_lock = threading.Lock()
_liveness_lock = threading.Lock()
_arcface_model = None
_deepface_class = None
_liveness_initialized = False


class FaceServiceUnavailableError(RuntimeError):
    """Falha controlada ao disponibilizar o processamento facial."""


class InvalidFaceImageError(ValueError):
    """A imagem recebida nao pode ser usada para cadastro biometrico."""


class InvalidFaceCountError(ValueError):
    """A imagem nao contem exatamente uma face valida."""


class LivenessServiceUnavailableError(RuntimeError):
    """Falha controlada ao disponibilizar o anti-spoofing passivo."""


def _load_deepface_class():
    # A importacao tambem e tardia para manter o startup nao facial leve.
    from deepface import DeepFace

    return DeepFace


def _get_deepface_class():
    global _deepface_class

    if _deepface_class is None:
        with _model_lock:
            if _deepface_class is None:
                try:
                    _deepface_class = _load_deepface_class()
                except Exception as exc:
                    LOGGER.exception("Nao foi possivel carregar a biblioteca facial.")
                    raise FaceServiceUnavailableError(
                        "Servico facial temporariamente indisponivel."
                    ) from exc

    return _deepface_class


def get_arcface_model():
    """Constroi o ArcFace uma unica vez, somente no primeiro uso facial."""
    global _arcface_model, _deepface_class

    if _arcface_model is None:
        with _model_lock:
            if _arcface_model is None:
                try:
                    deepface = _deepface_class or _load_deepface_class()
                    # Publica biblioteca e modelo somente depois de cada carga bem-sucedida.
                    model = deepface.build_model(MODEL_NAME)
                    _deepface_class = deepface
                    _arcface_model = model
                except Exception as exc:
                    LOGGER.exception(
                        "Nao foi possivel carregar o modelo facial ArcFace."
                    )
                    raise FaceServiceUnavailableError(
                        "Servico facial temporariamente indisponivel."
                    ) from exc

    return _arcface_model


def is_arcface_model_loaded():
    """Informa o estado do processo sem disparar o carregamento."""
    return _arcface_model is not None


def extract_faces(
    img,
    detector,
    align=True,
    enforce_detection=False,
    anti_spoofing=False,
):
    """Executa a deteccao legada sem construir o ArcFace antecipadamente."""
    deepface = _get_deepface_class()
    return deepface.extract_faces(
        img_path=img,
        detector_backend=detector,
        enforce_detection=enforce_detection,
        align=align,
        anti_spoofing=anti_spoofing,
    )


def _decode_image_bytes(image_bytes):
    import cv2
    import numpy as np

    if not image_bytes:
        raise InvalidFaceImageError("Imagem biometrica ausente.")

    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise InvalidFaceImageError("Arquivo de imagem invalido.")
    return image


def _extract_faces_with_passive_liveness(image, detector_backend):
    global _liveness_initialized

    if not _liveness_initialized:
        with _liveness_lock:
            if not _liveness_initialized:
                faces = extract_faces(
                    image,
                    detector_backend,
                    align=True,
                    enforce_detection=True,
                    anti_spoofing=True,
                )
                _liveness_initialized = True
                return faces

    return extract_faces(
        image,
        detector_backend,
        align=True,
        enforce_detection=True,
        anti_spoofing=True,
    )


def verify_passive_liveness(image_bytes, detector_backend="opencv"):
    """Executa o MiniFASNet sem persistir imagem, face, score ou landmarks.

    Esta verificacao e um anti-spoofing passivo experimental de imagem unica.
    Ela nao constitui prova definitiva de presenca fisica.
    """
    image = _decode_image_bytes(image_bytes)
    try:
        faces = _extract_faces_with_passive_liveness(image, detector_backend)
    except FaceServiceUnavailableError as exc:
        raise LivenessServiceUnavailableError(
            "Servico de liveness temporariamente indisponivel."
        ) from exc
    except (ImportError, ModuleNotFoundError) as exc:
        raise LivenessServiceUnavailableError(
            "Servico de liveness temporariamente indisponivel."
        ) from exc
    except ValueError as exc:
        message = str(exc).lower()
        if "torch" in message or "weight" in message:
            raise LivenessServiceUnavailableError(
                "Servico de liveness temporariamente indisponivel."
            ) from exc
        raise InvalidFaceCountError(
            "Nao foi possivel detectar uma face valida na imagem."
        ) from exc
    except Exception as exc:
        raise LivenessServiceUnavailableError(
            "Servico de liveness temporariamente indisponivel."
        ) from exc

    if len(faces) != 1:
        raise InvalidFaceCountError("A imagem deve conter exatamente uma face.")

    face = faces[0] if isinstance(faces[0], dict) else None
    if not face or "is_real" not in face or "antispoof_score" not in face:
        raise LivenessServiceUnavailableError(
            "Servico de liveness retornou resultado invalido."
        )

    is_real = face["is_real"]
    if not isinstance(is_real, bool):
        raise LivenessServiceUnavailableError(
            "Servico de liveness retornou resultado invalido."
        )

    try:
        score = float(face["antispoof_score"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise LivenessServiceUnavailableError(
            "Servico de liveness retornou resultado invalido."
        ) from exc
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise LivenessServiceUnavailableError(
            "Servico de liveness retornou resultado invalido."
        )

    return is_real, score


def generate_arcface_embedding(face_img):
    """Gera e normaliza o embedding usado pelas rotas faciais legadas."""
    import numpy as np

    get_arcface_model()
    deepface = _get_deepface_class()
    representation = deepface.represent(
        img_path=face_img,
        model_name=MODEL_NAME,
        detector_backend="skip",
        enforce_detection=False,
    )

    if not representation or "embedding" not in representation[0]:
        raise ValueError("O modelo facial nao retornou um embedding.")

    embedding = np.asarray(representation[0]["embedding"], dtype=np.float32)
    if embedding.ndim != 1 or embedding.size != EMBEDDING_DIMENSION:
        raise ValueError(f"Embedding ArcFace com dimensao inesperada: {embedding.size}")

    if not np.isfinite(embedding).all():
        raise ValueError("O embedding facial contem valores invalidos.")

    norm = np.linalg.norm(embedding)
    if not math.isfinite(float(norm)) or norm == 0:
        raise ValueError("Nao foi possivel normalizar o embedding.")

    normalized = embedding / norm
    if not np.isfinite(normalized).all():
        raise ValueError("Nao foi possivel normalizar o embedding.")

    return normalized.tolist()


def generate_biometric_embedding(image_bytes, detector_backend="opencv"):
    """Valida uma imagem em memoria e gera um embedding para uma unica face.

    A funcao nao persiste a imagem e nao executa identificacao facial. O chamador
    ja conhece o funcionario ao qual o vetor sera associado.
    """
    image = _decode_image_bytes(image_bytes)

    try:
        faces = extract_faces(
            image,
            detector_backend,
            align=True,
            enforce_detection=True,
        )
    except FaceServiceUnavailableError:
        raise
    except Exception as exc:
        raise InvalidFaceCountError(
            "Nao foi possivel detectar uma face valida na imagem."
        ) from exc

    if len(faces) != 1:
        raise InvalidFaceCountError("A imagem deve conter exatamente uma face.")

    face = faces[0].get("face") if isinstance(faces[0], dict) else None
    if face is None or not hasattr(face, "size") or face.size == 0:
        raise InvalidFaceCountError("A face detectada nao e valida.")

    try:
        embedding = generate_arcface_embedding(face)
    except FaceServiceUnavailableError:
        raise
    except Exception as exc:
        raise InvalidFaceImageError(
            "Nao foi possivel gerar a representacao facial."
        ) from exc

    if len(embedding) != EMBEDDING_DIMENSION or not all(
        math.isfinite(value) for value in embedding
    ):
        raise InvalidFaceImageError("A representacao facial gerada e invalida.")

    return embedding


def calcular_embedding_medio(lista_embeddings):
    """Normaliza embeddings ArcFace, calcula a media e normaliza o vetor final."""
    import numpy as np

    if not isinstance(lista_embeddings, (list, tuple)) or not lista_embeddings:
        raise InvalidFaceImageError("Nenhum embedding facial valido foi informado.")

    normalizados = []
    for embedding in lista_embeddings:
        try:
            vetor = np.asarray(embedding, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidFaceImageError(
                "A representacao facial gerada e invalida."
            ) from exc
        if vetor.ndim != 1 or vetor.size != EMBEDDING_DIMENSION:
            raise InvalidFaceImageError(
                f"Cada embedding facial deve possuir {EMBEDDING_DIMENSION} dimensoes."
            )
        if not np.isfinite(vetor).all():
            raise InvalidFaceImageError("O embedding facial contem valores invalidos.")

        norma = np.linalg.norm(vetor)
        if not math.isfinite(float(norma)) or norma == 0:
            raise InvalidFaceImageError("Embedding facial nao pode possuir norma zero.")
        normalizados.append(vetor / norma)

    media = np.mean(np.stack(normalizados), axis=0)
    norma_media = np.linalg.norm(media)
    if not math.isfinite(float(norma_media)) or norma_media == 0:
        raise InvalidFaceImageError("Nao foi possivel normalizar o embedding medio.")

    embedding_final = media / norma_media
    if (
        embedding_final.size != EMBEDDING_DIMENSION
        or not np.isfinite(embedding_final).all()
    ):
        raise InvalidFaceImageError("O embedding facial medio e invalido.")
    return embedding_final.tolist()


def cosine_distance(reference_embedding, candidate_embedding):
    """Calcula distancia cosseno entre dois vetores faciais normalizados."""
    import numpy as np

    reference = np.asarray(reference_embedding, dtype=np.float64)
    candidate = np.asarray(candidate_embedding, dtype=np.float64)
    for embedding in (reference, candidate):
        if embedding.ndim != 1 or embedding.size != EMBEDDING_DIMENSION:
            raise ValueError("Embedding facial com dimensao invalida.")
        if not np.isfinite(embedding).all():
            raise ValueError("Embedding facial contem valores invalidos.")

    reference_norm = np.linalg.norm(reference)
    candidate_norm = np.linalg.norm(candidate)
    if reference_norm == 0 or candidate_norm == 0:
        raise ValueError("Embedding facial nao pode possuir norma zero.")

    similarity = float(np.dot(reference / reference_norm, candidate / candidate_norm))
    similarity = max(-1.0, min(1.0, similarity))
    return 1.0 - similarity


def compare_face_embeddings(reference_embedding, candidate_embedding, max_distance):
    """Retorna a decisao 1:1 e a distancia usada na auditoria tecnica."""
    try:
        threshold = float(max_distance)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Threshold facial invalido.") from exc
    if not math.isfinite(threshold) or not 0 < threshold <= 2:
        raise ValueError("Threshold facial invalido.")

    distance = cosine_distance(reference_embedding, candidate_embedding)
    return distance <= threshold, distance


def verify_face_match(reference_embedding, candidate_embedding, max_distance):
    """Decide um match 1:1 usando limiar definido exclusivamente no servidor."""
    verified, _distance = compare_face_embeddings(
        reference_embedding,
        candidate_embedding,
        max_distance,
    )
    return verified


def _reset_for_tests():
    """Limpa apenas o cache em memoria para testes unitarios controlados."""
    global _arcface_model, _deepface_class, _liveness_initialized
    with _model_lock:
        _arcface_model = None
        _deepface_class = None
    with _liveness_lock:
        _liveness_initialized = False
