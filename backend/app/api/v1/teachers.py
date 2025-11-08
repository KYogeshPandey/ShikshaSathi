from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.teacher_schema import TeacherCreate, TeacherUpdate
from app.services.teacher_service import *

bp = Blueprint("teachers", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
def list_teachers_route():
    result = get_all_teachers()
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST"])
@jwt_required()
def create_teacher_route():
    try:
        payload = TeacherCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    tid = add_teacher(payload.dict())
    return jsonify({"success": True, "id": tid}), 201

@bp.route("/<tid>", methods=["GET"])
@jwt_required()
def get_teacher_route(tid):
    t = get_teacher_by_id(tid)
    if not t:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": t}), 200

@bp.route("/<tid>", methods=["PUT"])
@jwt_required()
def update_teacher_route(tid):
    try:
        payload = TeacherUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    update_teacher_data(tid, {k: v for k, v in payload.dict().items() if v is not None})
    return jsonify({"success": True}), 200

@bp.route("/<tid>", methods=["DELETE"])
@jwt_required()
def delete_teacher_route(tid):
    delete_teacher_data(tid)
    return jsonify({"success": True}), 200

@bp.route("/<tid>/assign_classroom", methods=["POST"])
@jwt_required()
def assign_classroom_route(tid):
    cid = request.json.get("classroom_id")
    assign_classroom_to_teacher(tid, cid)
    return jsonify({"success": True}), 200

@bp.route("/<tid>/remove_classroom", methods=["POST"])
@jwt_required()
def remove_classroom_route(tid):
    cid = request.json.get("classroom_id")
    remove_classroom_from_teacher(tid, cid)
    return jsonify({"success": True}), 200
