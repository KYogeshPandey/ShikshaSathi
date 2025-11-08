from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta 
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi         
import os

load_dotenv()

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    app.config['MONGODB_URI'] = os.getenv('MONGODB_URI')
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER')
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=1) 

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    jwt = JWTManager(app)

    try:
        # FINAL FIX: certifi for Windows + Atlas SSL
        client = MongoClient(
            app.config['MONGODB_URI'],
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where()
        )
        client.server_info()
        app.db = client["shiksha_sathi"]
        print("✅ MongoDB connected!")
    except Exception as e:
        print(f"⚠️  MongoDB: {e}")
        app.db = None

    # Register ALL blueprints here
    from app.api.v1.auth import bp as auth_bp
    from app.api.v1.students import bp as students_bp
    from app.api.v1.classrooms import bp as classrooms_bp
    from app.api.v1.attendance import bp as attendance_bp
    from app.api.v1.teachers import bp as teachers_bp
    app.register_blueprint(teachers_bp, url_prefix='/api/v1/teachers')
    app.register_blueprint(attendance_bp, url_prefix='/api/v1/attendance')
    app.register_blueprint(classrooms_bp, url_prefix='/api/v1/classrooms')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(students_bp, url_prefix='/api/v1/students')

    @app.route('/')
    def index():
        return {'app': 'ShikshaSathi', 'version': '1.0', 'status': 'running'}

    @app.route('/health')
    def health():
        return {'status': 'ok', 'database': 'connected' if app.db else 'disconnected'}

    return app
