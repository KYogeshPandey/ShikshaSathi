from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ...services.student_service import (
    add_student,
    get_students,
    get_student_by_id,
    update_student_data,
    delete_student_data,
    move_students_to_class,
)
from ...services.import_service import import_entities_from_csv
from ...utils.auth import requires_roles

bp = Blueprint("students", __name__)

# --- Student ka apna profile ---
@bp.route("/me", methods=["GET"])
@jwt_required(optional=True)
def get_my_profile_route():
    try:
        identity = get_jwt_identity()
        if not identity:
            profile = {
                "name": "Student One",
                "className": "Class 10-A",
                "rollNumber": "S001",
                "email": "student1@school.com",
                "username": "student1",
            }
            return jsonify({"success": True, "data": profile}), 200
        student = get_student_by_id(identity)
        if not student:
            profile = {
                "name": "Student One",
                "className": "Class 10-A",
                "rollNumber": "S001",
                "email": f"{identity}@school.com",
                "username": identity,
            }
            return jsonify({"success": True, "data": profile}), 200
        return jsonify({"success": True, "data": student}), 200
    except Exception as e:
        print(f"❌ Error in get_my_profile_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

# --- Public list (demo/legacy; admin dashboard ko /admin use karna chahiye) ---
@bp.route("/", methods=["GET"])
@jwt_required(optional=True)
def get_all_students_route():
    try:
        students = get_students()
        if students:
            return jsonify({"success": True, "data": students}), 200
        demo_students = [
            {"name": "Student One", "rollNumber": "S001", "className": "Class 10-A"},
            {"name": "Student Two", "rollNumber": "S002", "className": "Class 10-B"},
            {"name": "Student Three", "rollNumber": "S003", "className": "Class 9-A"},
        ]
        return jsonify({"success": True, "data": demo_students}), 200
    except Exception as e:
        print(f"❌ Error in get_all_students_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

# --- Admin CRUD + search ---
@bp.route("/admin", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def list_students_admin():
    try:
        classroom_id = request.args.get("classroom_id")
        q = (request.args.get("q") or "").strip().lower() or None
        students = get_students(classroom_id=classroom_id)
        if q:
            students = [
                s for s in students
                if q in str(s.get("name", "")).lower() or q in str(s.get("roll_no", "")).lower()
            ]
        return jsonify({"success": True, "data": students}), 200
    except Exception as e:
        print(f"❌ Error in list_students_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/admin", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def create_student_admin():
    try:
        payload = request.get_json() or {}
        new_id = add_student(payload)
        return jsonify({"success": True, "data": {"_id": new_id}}), 201
    except Exception as e:
        print(f"❌ Error in create_student_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/admin/<student_id>", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def get_student_admin(student_id):
    try:
        student = get_student_by_id(student_id)
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404
        return jsonify({"success": True, "data": student}), 200
    except Exception as e:
        print(f"❌ Error in get_student_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/admin/<student_id>", methods=["PUT", "PATCH"])
@jwt_required()
@requires_roles("admin")
def update_student_admin(student_id):
    try:
        payload = request.get_json() or {}
        update_student_data(student_id, payload)
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"❌ Error in update_student_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/admin/<student_id>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")
def delete_student_admin(student_id):
    try:
        delete_student_data(student_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"❌ Error in delete_student_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/admin/bulk-move", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def bulk_move_students_admin():
    try:
        payload = request.get_json() or {}
        student_ids = payload.get("student_ids") or []
        new_classroom_id = payload.get("new_classroom_id")
        if not student_ids or not new_classroom_id:
            return jsonify({
                "success": False,
                "message": "student_ids and new_classroom_id required"
            }), 400
        move_students_to_class(student_ids, new_classroom_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"❌ Error in bulk_move_students_admin: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

# -- Bulk Import (CSV) --
@bp.route("/import/csv", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def import_students_csv():
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "message": "CSV file required"}), 400
    result = import_entities_from_csv(f.read(), entity_type="student")
    return jsonify(result), 200 if result["success"] else 400

# -- (Optional) Bulk Export (CSV) --
from ...services.student_service import get_all_students
import csv
import io

@bp.route("/export/csv", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def export_students_csv():
    students = get_all_students()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "roll_no", "classroom_id", "email"])
    writer.writeheader()
    for s in students:
        writer.writerow({k: s.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    return(
        output.getvalue(),
        200,
        {
            "Content-Disposition": "attachment; filename=students.csv",
            "Content-type": "text/csv"
        }
    )