from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.attendance_schema import AttendanceCreate
from app.services.attendance_service import (
    add_attendance, get_all_attendance, get_attendance_by_id,
    update_attendance_data, delete_attendance_data
)

bp = Blueprint("attendance", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
def list_attendance_route():
    filter_params = {
        "student_id": request.args.get("student_id"),
        "classroom_id": request.args.get("classroom_id"),
        "date": request.args.get("date"),
    }
    filter_params = {k: v for k, v in filter_params.items() if v}
    result = get_all_attendance(filter_params)
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST"])
@jwt_required()
def create_attendance_route():
    try:
        payload = AttendanceCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    aid = add_attendance(payload.dict())
    return jsonify({"success": True, "id": aid}), 201

@bp.route("/<aid>", methods=["GET"])
@jwt_required()
def get_attendance_route(aid):
    att = get_attendance_by_id(aid)
    if not att:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": att}), 200

@bp.route("/<aid>", methods=["PUT"])
@jwt_required()
def update_attendance_route(aid):
    data = request.get_json()
    update_attendance_data(aid, data)
    return jsonify({"success": True}), 200

@bp.route("/<aid>", methods=["DELETE"])
@jwt_required()
def delete_attendance_route(aid):
    delete_attendance_data(aid)
    return jsonify({"success": True}), 200
