from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.student_schema import StudentCreate
from app.services.student_service import add_student, get_students
from app.utils.auth import requires_roles

bp = Blueprint("students", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")   # Only admin and teacher can see student list
def list_students_route():
    classroom_id = request.args.get("classroom_id")
    students = get_students(classroom_id)
    return jsonify({"success": True, "data": students}), 200

@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")              # Only admin can create student
def create_student_route():
    try:
        payload = StudentCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    sid = add_student(payload.dict())
    return jsonify({"success": True, "id": sid}), 201
