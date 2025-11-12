from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
import os

def create_app():
    load_dotenv()
    app = Flask(__name__)

    app.config['MONGODB_URI'] = os.environ.get('MONGODB_URI')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')

    JWTManager(app)

    # Register blueprints (order doesn't matter)
    from app.api.v1.auth import bp as auth_bp
    from app.api.v1.students import bp as students_bp
    from app.api.v1.teachers import bp as teachers_bp
    from app.api.v1.attendance import bp as attendance_bp
    from app.api.v1.classrooms import bp as classrooms_bp

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(students_bp, url_prefix='/api/v1/students')
    app.register_blueprint(teachers_bp, url_prefix='/api/v1/teachers')
    app.register_blueprint(attendance_bp, url_prefix='/api/v1/attendance')
    app.register_blueprint(classrooms_bp, url_prefix='/api/v1/classrooms')

    # CORS must be enabled globally
    CORS(app, supports_credentials=True)
    return app

app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ShikshaSathi Backend Server Starting...")
    print("=" * 60)
    print("📍 Server: http://localhost:5000")
    print("🔍 Health: http://localhost:5000/health")
    print("🔐 API: http://localhost:5000/api/v1")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
