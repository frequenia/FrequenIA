import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
VALID_APP_ENVIRONMENTS = {"development", "homologation", "production"}

if APP_ENV not in VALID_APP_ENVIRONMENTS:
    raise RuntimeError(
        "APP_ENV must be one of: development, homologation, production."
    )

secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is required to start the application.")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

if "*" in cors_origins:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must contain explicit origins.")

app = Flask(__name__)
app.config["SECRET_KEY"] = secret_key

if cors_origins:
    CORS(app, origins=cors_origins, supports_credentials=True)


@app.get("/health")
def health():
    return jsonify(status="ok")


from routes.views import views_bp
from routes.face import face_bp

app.register_blueprint(views_bp)
app.register_blueprint(face_bp)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=APP_ENV == "development",
    )
