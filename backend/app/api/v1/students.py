import os
import tempfile
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from app.schemas.student_schema import StudentCreate
from app.services.student_service import (
    add_student, get_students, get_student_by_id, update_student_data, delete_student_data
)
from app.utils.auth import requires_roles
from app.utils.file_upload import process_student_excel, extract_student_photos

bp = Blueprint("students", __name__)
PHOTOS_STATIC_FOLDER = os.path.join(os.path.dirname(__file__), "../../static/photos/")

def _cors_options_response(methods="GET,POST,PUT,DELETE,OPTIONS"):
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

@bp.route("/<sid>", methods=["GET", "OPTIONS"])
def get_student_route(sid):
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _get_student_route(sid)

@jwt_required()
@requires_roles("admin", "teacher")
def _get_student_route(sid):
    student = get_student_by_id(sid)
    if not student:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": student}), 200

@bp.route("/<sid>", methods=["PUT", "OPTIONS"])
def update_student_route(sid):
    if request.method == "OPTIONS":
        return _cors_options_response("PUT,OPTIONS")
    return _update_student_route(sid)

@jwt_required()
@requires_roles("admin")
def _update_student_route(sid):
    data = request.get_json()
    update_student_data(sid, data)
    return jsonify({"success": True}), 200

@bp.route("/<sid>", methods=["DELETE", "OPTIONS"])
def delete_student_route(sid):
    if request.method == "OPTIONS":
        return _cors_options_response("DELETE,OPTIONS")
    return _delete_student_route(sid)

@jwt_required()
@requires_roles("admin")
def _delete_student_route(sid):
    delete_student_data(sid)
    return jsonify({"success": True}), 200

# ---------- BULK CSV & PHOTO IMPORT BELOW ----------

@bp.route("/upload_csv", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def upload_students_csv():
    file = request.files.get("file")
    if not file or not file.filename.endswith((".xlsx", ".xls")):
        return jsonify({"success": False, "msg": "Excel file required!"}), 400
    temp_path = tempfile.mktemp(suffix=".xlsx")
    file.save(temp_path)
    students = process_student_excel(temp_path)
    os.remove(temp_path)
    created = []
    for s in students:
        sid = add_student(s)
        created.append(sid)
    return jsonify({"success": True, "created": created}), 201

@bp.route("/upload_photos", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def upload_photos_zip():
    file = request.files.get("file")
    if not file or not file.filename.endswith(".zip"):
        return jsonify({"success": False, "msg": "ZIP file required!"}), 400
    os.makedirs(PHOTOS_STATIC_FOLDER, exist_ok=True)
    temp_path = tempfile.mktemp(suffix=".zip")
    file.save(temp_path)
    extract_student_photos(temp_path, PHOTOS_STATIC_FOLDER)
    os.remove(temp_path)
    return jsonify({"success": True, "msg": "Photos extracted!"}), 200
