from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.attendance_schema import AttendanceCreate
from app.services.attendance_service import (
    add_attendance, get_all_attendance, get_attendance_by_id,
    update_attendance_data, delete_attendance_data, get_attendance_stats
)
from app.utils.auth import requires_roles

bp = Blueprint("attendance", __name__)

def _cors_options_response(methods="GET,POST,PUT,DELETE,OPTIONS"):
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response, 200

@bp.route("/", methods=["GET", "OPTIONS"])
def list_attendance_route():
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _list_attendance_route()

@jwt_required()
@requires_roles("admin", "teacher")
def _list_attendance_route():
    filter_params = {
        "student_id": request.args.get("student_id"),
        "classroom_id": request.args.get("classroom_id"),
        "date": request.args.get("date"),
    }
    filter_params = {k: v for k, v in filter_params.items() if v}
    result = get_all_attendance(filter_params)
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST", "OPTIONS"])
def create_attendance_route():
    if request.method == "OPTIONS":
        return _cors_options_response("POST,OPTIONS")
    return _create_attendance_route()

@jwt_required()
@requires_roles("admin", "teacher")
def _create_attendance_route():
    try:
        payload = AttendanceCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400
    aid = add_attendance(payload.dict())
    return jsonify({"success": True, "id": aid}), 201

@bp.route("/<aid>", methods=["GET", "OPTIONS"])
def get_attendance_route(aid):
    if request.method == "OPTIONS":
        return _cors_options_response("GET,OPTIONS")
    return _get_attendance_route(aid)

@jwt_required()
@requires_roles("admin", "teacher", "student")
def _get_attendance_route(aid):
    att = get_attendance_by_id(aid)
    if not att:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": att}), 200

@bp.route("/<aid>", methods=["PUT", "OPTIONS"])
def update_attendance_route(aid):
    if request.method == "OPTIONS":
        return _cors_options_response("PUT,OPTIONS")
    return _update_attendance_route(aid)

@jwt_required()
@requires_roles("admin")
def _update_attendance_route(aid):
    data = request.get_json()
    update_attendance_data(aid, data)
    return jsonify({"success": True}), 200

@bp.route("/<aid>", methods=["DELETE", "OPTIONS"])
def delete_attendance_route(aid):
    if request.method == "OPTIONS":
        return _cors_options_response("DELETE,OPTIONS")
    return _delete_attendance_route(aid)

@jwt_required()
@requires_roles("admin")
def _delete_attendance_route(aid):
    delete_attendance_data(aid)
    return jsonify({"success": True}), 200

@bp.route("/stats", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def attendance_stats_route():
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    classroom_id = request.args.get("classroom_id")
    student_id = request.args.get("student_id")
    stats = get_attendance_stats(date_from, date_to, classroom_id, student_id)
    return jsonify({"success": True, "data": stats}), 200
