from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.schemas.classroom_schema import ClassroomCreate
from app.services.classroom_service import (
    add_classroom, get_all_classrooms,
    get_classroom_by_id, update_classroom_data, delete_classroom_data,
    assign_students, unassign_students, list_students_in_classroom
)
from app.utils.auth import requires_roles  # <-- IMPORT DECORATOR HERE


bp = Blueprint("classrooms", __name__)


@bp.route("/", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")  # Only admin and teacher can list classrooms
def list_classrooms_route():
    result = get_all_classrooms()
    return jsonify({"success": True, "data": result}), 200


@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")   # Only admin can create classrooms
def create_classroom_route():
    try:
        payload = ClassroomCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    cdict = payload.dict()
    if "student_ids" not in cdict:
        cdict["student_ids"] = []
    cid = add_classroom(cdict)
    return jsonify({"success": True, "id": cid}), 201


@bp.route("/<cid>", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher", "student")  # All authenticated users can view details
def get_classroom_route(cid):
    c = get_classroom_by_id(cid)
    if not c:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": c}), 200


@bp.route("/<cid>", methods=["PUT"])
@jwt_required()
@requires_roles("admin")  # Only admin can update classroom
def update_classroom_route(cid):
    data = request.get_json()
    update_classroom_data(cid, data)
    return jsonify({"success": True}), 200


@bp.route("/<cid>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")  # Only admin can delete classroom
def delete_classroom_route(cid):
    delete_classroom_data(cid)
    return jsonify({"success": True}), 200


# --- Student-Classroom endpoints ---


@bp.route("/<cid>/add_students", methods=["POST"])
@jwt_required()
@requires_roles("admin", "teacher")   # Both admin and teacher may assign students
def add_students_route(cid):
    data = request.get_json()
    student_ids = data.get("student_ids", [])
    assign_students(cid, student_ids)
    return jsonify({"success": True}), 200


@bp.route("/<cid>/remove_students", methods=["POST"])
@jwt_required()
@requires_roles("admin", "teacher")
def remove_students_route(cid):
    data = request.get_json()
    student_ids = data.get("student_ids", [])
    unassign_students(cid, student_ids)
    return jsonify({"success": True}), 200


@bp.route("/<cid>/students", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")  # Only admin and teacher can view all students of a class
def classroom_students_route(cid):
    students = list_students_in_classroom(cid)
    return jsonify({"success": True, "student_ids": students}), 200
