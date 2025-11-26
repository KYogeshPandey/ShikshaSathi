from .auth import bp as auth_bp
from .students import bp as students_bp
from .teachers import bp as teachers_bp
from .classrooms import bp as classrooms_bp
from .attendance import bp as attendance_bp
from .reports import bp as reports_bp
from .subjects import bp as subjects_bp
from .logs import bp as logs_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(students_bp, url_prefix="/api/v1/students")
    app.register_blueprint(teachers_bp, url_prefix="/api/v1/teachers")
    app.register_blueprint(classrooms_bp, url_prefix="/api/v1/classrooms")
    app.register_blueprint(attendance_bp, url_prefix="/api/v1/attendance")
    app.register_blueprint(reports_bp, url_prefix="/api/v1/reports")
    app.register_blueprint(subjects_bp, url_prefix="/api/v1/subjects")
    app.register_blueprint(logs_bp, url_prefix="/api/v1/logs")
