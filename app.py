from flask import Flask
from flask_cors import CORS

from routes.views import views_bp
from routes.face import face_bp
from routes.mobile import mobile_bp

app = Flask(__name__)
app.secret_key = "chave_super_secreta_123" 
CORS(app)

app.register_blueprint(views_bp)
app.register_blueprint(face_bp)
app.register_blueprint(mobile_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)