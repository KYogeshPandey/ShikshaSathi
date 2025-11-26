from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ...services.subject_service import (
    add_subject,
    get_all_subjects,
    get_subject_by_id,
    update_subject_data,
    delete_subject_data,
)
from ...utils.auth import requires_roles

bp = Blueprint("subjects", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def list_subjects_route():
    try:
        filters = {
            "standard": request.args.get("standard") or None,
            "classroom_id": request.args.get("classroom_id") or None,
            "code": request.args.get("code") or None,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        subjects = get_all_subjects(filters)
        return jsonify({"success": True, "data": subjects}), 200
    except Exception as e:
        print(f"❌ Error in list_subjects_route: {e}")
        return jsonify({"success": False, "message": "Failed to fetch subjects"}), 500

@bp.route("/<subject_id>", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def get_subject_route(subject_id):
    try:
        subject = get_subject_by_id(subject_id)
        if not subject:
            return jsonify({"success": False, "message": "Subject not found"}), 404
        return jsonify({"success": True, "data": subject}), 200
    except Exception as e:
        print(f"❌ Error in get_subject_route: {e}")
        return jsonify({"success": False, "message": "Failed to fetch subject"}), 500

@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def create_subject_route():
    try:
        data = request.get_json() or {}
        if not data.get("name"):
            return jsonify({"success": False, "message": "Field 'name' is required"}), 400
        sid = add_subject(data)
        return jsonify({"success": True, "id": sid}), 201
    except Exception as e:
        print(f"❌ Error in create_subject_route: {e}")
        return jsonify({"success": False, "message": "Failed to create subject"}), 500

@bp.route("/<subject_id>", methods=["PUT", "PATCH"])
@jwt_required()
@requires_roles("admin")
def update_subject_route(subject_id):
    try:
        data = request.get_json() or {}
        update_subject_data(subject_id, data)
        return jsonify({"success": True, "message": "Subject updated"}), 200
    except Exception as e:
        print(f"❌ Error in update_subject_route: {e}")
        return jsonify({"success": False, "message": "Failed to update subject"}), 500

@bp.route("/<subject_id>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")
def delete_subject_route(subject_id):
    try:
        hard = request.args.get("hard", "false").lower() in ("1", "true", "yes")
        delete_subject_data(subject_id, hard=hard)
        return jsonify({"success": True, "message": "Subject deleted"}), 200
    except Exception as e:
        print(f"❌ Error in delete_subject_route: {e}")
        return jsonify({"success": False, "message": "Failed to delete subject"}), 500
