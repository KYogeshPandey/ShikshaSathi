from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
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

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    jwt = JWTManager(app)

    # --- JWT custom claims loader (role-based access) ---
    @jwt.user_identity_loader
    def user_identity_lookup(user):
        # we use username for identity, change to _id if you wish (must match what you set as identity)
        if isinstance(user, dict):
            return user.get("username")
        return user

    @jwt.additional_claims_loader
    def add_claims_to_access_token(user):
        # user param here will be the identity you pass in create_access_token()
        # so make sure it has 'role'
        # If you pass a string as identity, you must provide role in 'additional_claims' in login
        if isinstance(user, dict) and "role" in user:
            return {"role": user["role"]}
        # fallback: don't break old tokens
        return {}

    try:
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
    from app.api.v1.reports import bp as report_bp
  
    # add new blueprints below as needed!
    app.register_blueprint(report_bp, url_prefix='/api/v1/attendance')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(students_bp, url_prefix='/api/v1/students')
    app.register_blueprint(classrooms_bp, url_prefix='/api/v1/classrooms')
    # ...add other blueprints...

    @app.route('/')
    def index():
        return {'app': 'ShikshaSathi', 'version': '1.0', 'status': 'running'}

    @app.route('/health')
    def health():
        return {'status': 'ok', 'database': 'connected' if app.db else 'disconnected'}

    return app
