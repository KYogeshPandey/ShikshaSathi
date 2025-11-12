from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.teacher_schema import TeacherCreate, TeacherUpdate
from app.services.teacher_service import *
from app.utils.auth import requires_roles

bp = Blueprint("teachers", __name__)

def _cors_options_response(methods="GET,POST,PUT,DELETE,OPTIONS"):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response, 200

@bp.route("/", methods=["GET", "OPTIONS"])
def list_teachers_route():
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _list_teachers_route()

@jwt_required()
@requires_roles("admin")
def _list_teachers_route():
    result = get_all_teachers()
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST", "OPTIONS"])
def create_teacher_route():
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _create_teacher_route()

@jwt_required()
@requires_roles("admin")
def _create_teacher_route():
    try:
        payload = TeacherCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    tid = add_teacher(payload.dict())
    return jsonify({"success": True, "id": tid}), 201

@bp.route("/<tid>", methods=["GET", "OPTIONS"])
def get_teacher_route(tid):
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _get_teacher_route(tid)

@jwt_required()
@requires_roles("admin", "teacher")
def _get_teacher_route(tid):
    t = get_teacher_by_id(tid)
    if not t:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": t}), 200

@bp.route("/<tid>", methods=["PUT", "OPTIONS"])
def update_teacher_route(tid):
    if request.method == "OPTIONS":
        return _cors_options_response("PUT,OPTIONS")
    return _update_teacher_route(tid)

@jwt_required()
@requires_roles("admin")
def _update_teacher_route(tid):
    try:
        payload = TeacherUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    update_teacher_data(tid, {k: v for k, v in payload.dict().items() if v is not None})
    return jsonify({"success": True}), 200

@bp.route("/<tid>", methods=["DELETE", "OPTIONS"])
def delete_teacher_route(tid):
    if request.method == "OPTIONS":
        return _cors_options_response("DELETE,OPTIONS")
    return _delete_teacher_route(tid)

@jwt_required()
@requires_roles("admin")
def _delete_teacher_route(tid):
    delete_teacher_data(tid)
    return jsonify({"success": True}), 200

@bp.route("/<tid>/assign_classroom", methods=["POST", "OPTIONS"])
def assign_classroom_route(tid):
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _assign_classroom_route(tid)

@jwt_required()
@requires_roles("admin")
def _assign_classroom_route(tid):
    cid = request.json.get("classroom_id")
    assign_classroom_to_teacher(tid, cid)
    return jsonify({"success": True}), 200

@bp.route("/<tid>/remove_classroom", methods=["POST", "OPTIONS"])
def remove_classroom_route(tid):
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _remove_classroom_route(tid)

@jwt_required()
@requires_roles("admin")
def _remove_classroom_route(tid):
    cid = request.json.get("classroom_id")
    remove_classroom_from_teacher(tid, cid)
    return jsonify({"success": True}), 200
