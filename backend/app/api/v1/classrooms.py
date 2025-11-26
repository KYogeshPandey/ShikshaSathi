from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ...services.classroom_service import (
    add_classroom,
    get_all_classrooms,
    get_classroom_by_id,
    update_classroom_data,
    delete_classroom_data,
    assign_students,
    unassign_students,
    list_students_in_classroom,
)
from ...services.import_service import import_entities_from_csv
from ...utils.auth import requires_roles
import csv
import io

bp = Blueprint("classrooms", __name__)

DEMO_CLASSROOMS = [
    {
        "_id": "10th A",
        "name": "10th A",
        "label": "10th A",
        "section": "A",
        "standard": "10",
        "subjects": ["Maths", "Science", "English"],
    },
    {
        "_id": "10th B",
        "name": "10th B",
        "label": "10th B",
        "section": "B",
        "standard": "10",
        "subjects": ["Physics", "Chemistry", "English"],
    },
    {
        "_id": "9th A",
        "name": "9th A",
        "label": "9th A",
        "section": "A",
        "standard": "9",
        "subjects": ["Biology", "Maths", "English"],
    },
]

@bp.route("/", methods=["GET"])
def get_classrooms_route():
    """Saare classroom list karo (DB, fallback demo)."""
    try:
        classrooms = get_all_classrooms() or []
        if classrooms:
            return jsonify({"success": True, "data": classrooms}), 200
    except Exception as e:
        print(f"⚠️ DB error in get_classrooms, fallback to demo: {e}")
    return jsonify({"success": True, "data": DEMO_CLASSROOMS}), 200

@bp.route("/lassroom_id>", methods=["GET"])
def get_classroom_route(classroom_id):
    """Single class details (id/name/label), fallback demo."""
    try:
        classroom = get_classroom_by_id(classroom_id)
        if classroom:
            return jsonify({"success": True, "data": classroom}), 200
    except Exception as e:
        print(f"⚠️ Error in get_classroom_by_id: {e}")

    classroom = next(
        (
            c
            for c in DEMO_CLASSROOMS
            if c["_id"] == classroom_id
            or c.get("name") == classroom_id
            or c.get("label") == classroom_id
        ),
        None,
    )
    if not classroom:
        return jsonify({"success": False, "message": "Classroom not found"}), 404
    return jsonify({"success": True, "data": classroom}), 200

# --- CRUD (admin only) ---

@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def create_classroom_route():
    try:
        data = request.get_json() or {}
        if not data.get("name"):
            return jsonify({"success": False, "msg": "Field 'name' required"}), 400
        cid = add_classroom(data)
        return jsonify({"success": True, "id": cid}), 201
    except Exception as e:
        print(f"❌ Error in create_classroom_route: {e}")
        return jsonify({"success": False, "msg": "Failed to create"}), 500

@bp.route("/lassroom_id>", methods=["PUT", "PATCH"])
@jwt_required()
@requires_roles("admin")
def update_classroom_route(classroom_id):
    try:
        data = request.get_json() or {}
        update_classroom_data(classroom_id, data)
        return jsonify({"success": True, "msg": "Classroom updated"}), 200
    except Exception as e:
        print(f"❌ Error in update_classroom_route: {e}")
        return jsonify({"success": False, "msg": "Failed to update"}), 500

@bp.route("/lassroom_id>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")
def delete_classroom_route(classroom_id):
    try:
        delete_classroom_data(classroom_id)
        return jsonify({"success": True, "msg": "Classroom deleted"}), 200
    except Exception as e:
        print(f"❌ Error in delete_classroom_route: {e}")
        return jsonify({"success": False, "msg": "Failed to delete"}), 500

# --- Student assign/unassign (admin only) ---

@bp.route("/lassroom_id>/students", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def list_class_students_route(classroom_id):
    try:
        student_ids = list_students_in_classroom(classroom_id)
        return jsonify({"success": True, "data": student_ids}), 200
    except Exception as e:
        print(f"❌ Error in list_class_students_route: {e}")
        return jsonify({"success": False, "msg": "Fetch students error"}), 500

@bp.route("/lassroom_id>/students/assign", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def assign_students_route(classroom_id):
    try:
        data = request.get_json() or {}
        student_ids = data.get("student_ids") or []
        if not isinstance(student_ids, list) or not student_ids:
            return jsonify({"success": False, "msg": "Field 'student_ids' must be a non-empty list"}), 400
        assign_students(classroom_id, student_ids)
        return jsonify({"success": True, "msg": "Students assigned"}), 200
    except Exception as e:
        print(f"❌ Error in assign_students_route: {e}")
        return jsonify({"success": False, "msg": "Failed to assign"}), 500

@bp.route("/lassroom_id>/students/unassign", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def unassign_students_route(classroom_id):
    try:
        data = request.get_json() or {}
        student_ids = data.get("student_ids") or []
        if not isinstance(student_ids, list) or not student_ids:
            return jsonify({"success": False, "msg": "Field 'student_ids' must be a non-empty list"}), 400
        unassign_students(classroom_id, student_ids)
        return jsonify({"success": True, "msg": "Students unassigned"}), 200
    except Exception as e:
        print(f"❌ Error in unassign_students_route: {e}")
        return jsonify({"success": False, "msg": "Failed to unassign"}), 500

# --- Bulk Import (CSV) ---

@bp.route("/import/csv", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def import_classrooms_csv():
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "message": "CSV file required"}), 400
    result = import_entities_from_csv(f.read(), entity_type="classroom")
    return jsonify(result), 200 if result["success"] else 400

# --- (Optional) Bulk Export (CSV) ---

@bp.route("/export/csv", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def export_classrooms_csv():
    classrooms = get_all_classrooms()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "standard", "section", "label"])
    writer.writeheader()
    for cls in classrooms:
        writer.writerow({k: cls.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    return(
        output.getvalue(),
        200,
        {
            "Content-Disposition": "attachment; filename=classrooms.csv",
            "Content-type": "text/csv"
        }
    )
