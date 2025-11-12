from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.student_schema import StudentCreate
from app.services.student_service import add_student, get_students
from app.utils.auth import requires_roles

bp = Blueprint("students", __name__)

def _cors_options_response(methods="GET,POST,OPTIONS"):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response, 200

@bp.route("/", methods=["GET", "OPTIONS"])
def list_students_route():
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _list_students_route()

@jwt_required()
@requires_roles("admin", "teacher")
def _list_students_route():
    classroom_id = request.args.get("classroom_id")
    students = get_students(classroom_id)
    return jsonify({"success": True, "data": students}), 200

@bp.route("/", methods=["POST", "OPTIONS"])
def create_student_route():
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _create_student_route()

@jwt_required()
@requires_roles("admin")
def _create_student_route():
    try:
        payload = StudentCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    sid = add_student(payload.dict())
    return jsonify({"success": True, "id": sid}), 201
