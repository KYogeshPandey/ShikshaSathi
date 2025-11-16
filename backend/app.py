from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
import os
import certifi
import datetime

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # ===== CONFIGURATION =====
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret-key')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'fallback-jwt-key')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(
        seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))
    )
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'static/uploads')
    
    # ===== CORS CONFIGURATION =====
    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',')
    CORS(app, resources={
        r"/api/*": {
            "origins": cors_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "expose_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # ===== JWT MANAGER =====
    jwt = JWTManager(app)
    
    # ===== MONGODB CONNECTION =====
    mongodb_uri = os.getenv('MONGODB_URI')
    
    if not mongodb_uri:
        print("⚠️ WARNING: MONGODB_URI not found in environment variables!")
        app.config['mongodb_client'] = None
        app.config['db'] = None
    else:
        try:
            print("🔄 Connecting to MongoDB Atlas...")
            
            # ✅ FIXED: SSL bypass for OpenSSL 1.1.1q
            client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                maxPoolSize=10,
                minPoolSize=1,
                retryWrites=True,
                tls=True,
                tlsAllowInvalidCertificates=True  # ✅ Critical fix for SSL error
            )
            
            # Test the connection
            client.admin.command('ping')
            
            # Get database name from URI or use default
            db_name = os.getenv('MONGODB_DB_NAME', 'shiksha_sathi')
            db = client[db_name]
            
            # Store in app config for access in routes
            app.config['mongodb_client'] = client
            app.config['db'] = db
            
            print(f"✅ Successfully connected to MongoDB Atlas!")
            print(f"📊 Database: {db_name}")
            
            # List collections (for debugging)
            collections = db.list_collection_names()
            print(f"📁 Available collections: {collections if collections else 'None (empty DB)'}")
            
        except ServerSelectionTimeoutError as e:
            print(f"❌ MongoDB Connection Timeout Error")
            print("⚠️ Possible issues:")
            print("   1. Check your IP whitelist in MongoDB Atlas")
            print("   2. Verify username/password in connection string")
            print("   3. Check network connectivity")
            print("⚠️ Running in DEMO mode with fallback data")
            app.config['mongodb_client'] = None
            app.config['db'] = None
            
        except Exception as e:
            print(f"❌ MongoDB Connection Error: {str(e)}")
            print("⚠️ Running in DEMO mode")
            app.config['mongodb_client'] = None
            app.config['db'] = None
    
    # ===== REGISTER BLUEPRINTS =====
    from app.api.v1.auth import bp as auth_bp
    from app.api.v1.students import bp as students_bp
    from app.api.v1.classrooms import bp as classrooms_bp
    from app.api.v1.attendance import bp as attendance_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(students_bp, url_prefix='/api/v1/students')
    app.register_blueprint(classrooms_bp, url_prefix='/api/v1/classrooms')
    app.register_blueprint(attendance_bp, url_prefix='/api/v1/attendance')
    
    # ===== HEALTH CHECK ROUTES =====
    @app.route('/')
    def index():
        return jsonify({
            'app': 'ShikshaSathi API',
            'version': '1.0.0',
            'status': 'running',
            'timestamp': datetime.datetime.utcnow().isoformat()
        })
    
    @app.route('/health')
    def health():
        db_status = 'connected' if app.config.get('db') is not None else 'disconnected'
        return jsonify({
            'status': 'ok',
            'database': db_status,
            'message': 'Running in demo mode' if db_status == 'disconnected' else 'All systems operational',
            'timestamp': datetime.datetime.utcnow().isoformat()
        })
    
    @app.route('/api/v1/test-db')
    def test_db():
        """Test database connection endpoint"""
        db = app.config.get('db')
        
        if db is None:
            return jsonify({
                'success': False,
                'message': 'Database not connected - Running in DEMO mode',
                'note': 'Login works with demo users: admin1/admin123',
                'error': 'MongoDB client is None'
            }), 200
        
        try:
            # Test database operation
            server_info = app.config['mongodb_client'].server_info()
            collections = db.list_collection_names()
            
            return jsonify({
                'success': True,
                'message': 'Database connected successfully',
                'database': db.name,
                'collections': collections,
                'mongodb_version': server_info.get('version', 'unknown')
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Database connection test failed',
                'error': str(e)
            }), 500
    
    # ===== ERROR HANDLERS =====
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'error': 'Not Found',
            'message': 'The requested resource was not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'error': 'Internal Server Error',
            'message': str(error)
        }), 500
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            'success': False,
            'error': 'File Too Large',
            'message': f'Maximum file size is {app.config["MAX_CONTENT_LENGTH"]} bytes'
        }), 413
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'success': False,
            'message': 'Token has expired',
            'error': 'token_expired'
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Invalid token',
            'error': 'invalid_token'
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Authorization token is missing',
            'error': 'authorization_required'
        }), 401
    
    return app

# ===== CREATE APP INSTANCE =====
app = create_app()

# ===== HELPER FUNCTION TO GET DB =====
def get_db():
    """Helper function to get database instance"""
    from flask import current_app
    return current_app.config.get('db')

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 ShikshaSathi Backend Server Starting...")
    print("=" * 70)
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    print(f"📍 Server URL: http://localhost:{port}")
    print(f"🔍 Health Check: http://localhost:{port}/health")
    print(f"🧪 DB Test: http://localhost:{port}/api/v1/test-db")
    print(f"🔐 Auth API: http://localhost:{port}/api/v1/auth/login")
    print(f"🐛 Debug Mode: {debug}")
    print(f"🌍 Environment: {os.getenv('FLASK_ENV', 'development')}")
    print("\n💡 Demo Login Credentials:")
    print("   👤 Username: admin1")
    print("   🔒 Password: admin123")
    print("=" * 70)
    print("\n✅ Press Ctrl+C to stop the server\n")
    
    app.run(debug=debug, host=host, port=port)
