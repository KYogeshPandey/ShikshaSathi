from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

def create_app():
    app = Flask(__name__)
    
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    app.config['MONGODB_URI'] = os.getenv('MONGODB_URI')
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER')
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))
    
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    jwt = JWTManager(app)
    
    try:
        client = MongoClient(app.config['MONGODB_URI'], serverSelectionTimeoutMS=5000)
        client.server_info()
        app.db = client.get_default_database()
        print("✅ MongoDB connected!")
    except Exception as e:
        print(f"⚠️  MongoDB: {e}")
        app.db = None
    
    from app.api.v1.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    
    @app.route('/')
    def index():
        return {'app': 'ShikshaSathi', 'version': '1.0', 'status': 'running'}
    
    @app.route('/health')
    def health():
        return {'status': 'ok', 'database': 'connected' if app.db else 'disconnected'}
    
    return app