FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        build-essential \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Mantem os pesos exigidos pelo reconhecimento facial dentro da imagem. O
# download maior usa retomada e repeticao porque o downloader interno do
# DeepFace nao retoma uma transferencia interrompida.
RUN mkdir -p /root/.deepface/weights \
    && python -c "from deepface.modules import modeling; modeling.build_model(task='spoofing', model_name='Fasnet')" \
    && curl --fail --location \
        --retry 8 --retry-all-errors --retry-delay 5 --retry-max-time 1200 \
        --continue-at - \
        --output /root/.deepface/weights/arcface_weights.h5 \
        https://github.com/serengil/deepface_models/releases/download/v1.0/arcface_weights.h5 \
    && python -c "from deepface.modules import modeling; modeling.build_model(task='facial_recognition', model_name='ArcFace')"

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local
COPY --from=builder /root/.deepface /root/.deepface

COPY . .

EXPOSE 5000

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 1 --timeout 300 app:app"]
