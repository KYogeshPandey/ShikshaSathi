from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.classroom_schema import ClassroomCreate
from app.services.classroom_service import (
    add_classroom, get_all_classrooms, get_classroom_by_id,
    update_classroom_data, delete_classroom_data, assign_students,
    unassign_students, list_students_in_classroom
)
from app.utils.auth import requires_roles

bp = Blueprint("classrooms", __name__)

def _cors_options_response(methods="GET,POST,PUT,DELETE,OPTIONS"):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response, 200

@bp.route("/", methods=["GET", "OPTIONS"])
def list_classrooms_route():
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _list_classrooms_route()

@jwt_required()
@requires_roles("admin", "teacher")
def _list_classrooms_route():
    result = get_all_classrooms()
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST", "OPTIONS"])
def create_classroom_route():
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _create_classroom_route()

@jwt_required()
@requires_roles("admin")
def _create_classroom_route():
    try:
        payload = ClassroomCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400
    cdict = payload.dict()
    if "student_ids" not in cdict:
        cdict["student_ids"] = []
    cid = add_classroom(cdict)
    return jsonify({"success": True, "id": cid}), 201

@bp.route("/<cid>", methods=["GET", "OPTIONS"])
def get_classroom_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _get_classroom_route(cid)

@jwt_required()
@requires_roles("admin", "teacher", "student")
def _get_classroom_route(cid):
    c = get_classroom_by_id(cid)
    if not c:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": c}), 200

@bp.route("/<cid>", methods=["PUT", "OPTIONS"])
def update_classroom_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("PUT,OPTIONS")
    return _update_classroom_route(cid)

@jwt_required()
@requires_roles("admin")
def _update_classroom_route(cid):
    data = request.get_json()
    update_classroom_data(cid, data)
    return jsonify({"success": True}), 200

@bp.route("/<cid>", methods=["DELETE", "OPTIONS"])
def delete_classroom_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("DELETE,OPTIONS")
    return _delete_classroom_route(cid)

@jwt_required()
@requires_roles("admin")
def _delete_classroom_route(cid):
    delete_classroom_data(cid)
    return jsonify({"success": True}), 200

@bp.route("/<cid>/add_students", methods=["POST", "OPTIONS"])
def add_students_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _add_students_route(cid)

@jwt_required()
@requires_roles("admin", "teacher")
def _add_students_route(cid):
    data = request.get_json()
    student_ids = data.get("student_ids", [])
    assign_students(cid, student_ids)
    return jsonify({"success": True}), 200

@bp.route("/<cid>/remove_students", methods=["POST", "OPTIONS"])
def remove_students_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _remove_students_route(cid)

@jwt_required()
@requires_roles("admin", "teacher")
def _remove_students_route(cid):
    data = request.get_json()
    student_ids = data.get("student_ids", [])
    unassign_students(cid, student_ids)
    return jsonify({"success": True}), 200

@bp.route("/<cid>/students", methods=["GET", "OPTIONS"])
def classroom_students_route(cid):
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _classroom_students_route(cid)

@jwt_required()
@requires_roles("admin", "teacher")
def _classroom_students_route(cid):
    students = list_students_in_classroom(cid)
    return jsonify({"success": True, "student_ids": students}), 200
