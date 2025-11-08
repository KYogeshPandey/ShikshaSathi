from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.classroom_schema import ClassroomCreate
from app.services.classroom_service import (
    add_classroom, get_all_classrooms,
    get_classroom_by_id, update_classroom_data, delete_classroom_data
)

bp = Blueprint("classrooms", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
def list_classrooms_route():
    result = get_all_classrooms()
    return jsonify({"success": True, "data": result}), 200

@bp.route("/", methods=["POST"])
@jwt_required()
def create_classroom_route():
    try:
        payload = ClassroomCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    cid = add_classroom(payload.dict())
    return jsonify({"success": True, "id": cid}), 201

@bp.route("/<cid>", methods=["GET"])
@jwt_required()
def get_classroom_route(cid):
    c = get_classroom_by_id(cid)
    if not c:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": c}), 200

@bp.route("/<cid>", methods=["PUT"])
@jwt_required()
def update_classroom_route(cid):
    data = request.get_json()
    update_classroom_data(cid, data)
    return jsonify({"success": True}), 200

@bp.route("/<cid>", methods=["DELETE"])
@jwt_required()
def delete_classroom_route(cid):
    delete_classroom_data(cid)
    return jsonify({"success": True}), 200
