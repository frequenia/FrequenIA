FROM python:3.10-slim

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
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Baixa somente os pesos do anti-spoofing durante o build. O modelo continua
# sendo instanciado de forma lazy no primeiro uso e o ArcFace nao e carregado.
RUN mkdir -p /root/.deepface/weights \
    && python -c "from deepface.modules import modeling; modeling.build_model(task='spoofing', model_name='Fasnet')"

COPY . .

EXPOSE 5000

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 1 --timeout 300 app:app"]
