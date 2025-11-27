from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from pydantic import ValidationError
from bson import ObjectId

# Import Schemas
from ...schemas.teacher_schema import TeacherCreate, TeacherUpdate

# Import Services
from ...services.teacher_service import (
    get_all_teachers,
    add_teacher,
    get_teacher_by_id,
    update_teacher_data,
    delete_teacher_data,
    assign_classroom_to_teacher,
    remove_classroom_from_teacher,
)
# Assuming you have a service/db accessor for classrooms or teachers
from ...core.db import get_db 

from ...services.import_service import import_entities_from_csv
from ...utils.auth import requires_roles
import csv
import io

bp = Blueprint("teachers", __name__)

# ==========================================
# 👇 NEW ROUTE: Get My Classes (For Teacher Dashboard)
# ==========================================
@bp.route("/me/classes", methods=["GET"])
@jwt_required()
@requires_roles("teacher", "admin") # Allow teachers to access this
def get_my_classes():
    try:
        current_user_id = get_jwt_identity()
        
        # 1. Find Teacher Document by User ID (which is stored in JWT identity)
        # We assume the 'teachers' collection uses the same ID as the auth user
        # OR 'teachers' document has a field 'user_id'.
        # Let's try fetching directly by ID first.
        teacher = get_teacher_by_id(current_user_id)
        
        if not teacher:
            return jsonify({"success": False, "msg": "Teacher profile not found"}), 404
            
        assigned_ids = teacher.get("assigned_classrooms", [])
        
        if not assigned_ids:
            return jsonify([]), 200
            
        # 2. Fetch Classroom Details
        db = get_db()
        # Convert string IDs to ObjectIds (filter out invalid ones)
        c_oids = [ObjectId(cid) for cid in assigned_ids if ObjectId.is_valid(cid)]
        
        if not c_oids:
             return jsonify([]), 200

        classrooms_cursor = db.classrooms.find({"_id": {"$in": c_oids}})
        
        results = []
        for c in classrooms_cursor:
            c["_id"] = str(c["_id"])
            # Optional: Include student count for UI
            c["student_count"] = len(c.get("student_ids", []))
            results.append(c)

        return jsonify(results), 200

    except Exception as e:
        print(f"❌ Error in get_my_classes: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================
# Existing Routes
# ==========================================

@bp.route("/", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def list_teachers_route():
    teachers = get_all_teachers()
    return jsonify({"success": True, "data": teachers}), 200


@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def create_teacher_route():
    try:
        payload = TeacherCreate(**request.get_json())
        tid = add_teacher(payload.dict())
        return jsonify({"success": True, "id": tid}), 201
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400
    except Exception as e:
        print(f"❌ Error in create_teacher_route: {e}")
        return jsonify({"success": False, "message": "Failed to create teacher"}), 500


@bp.route("/<tid>", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def get_teacher_route(tid):
    t = get_teacher_by_id(tid)
    if not t:
        return jsonify({"success": False, "message": "Not found"}), 404
    return jsonify({"success": True, "data": t}), 200


@bp.route("/<tid>", methods=["PUT", "PATCH"])
@jwt_required()
@requires_roles("admin")
def update_teacher_route(tid):
    try:
        payload = TeacherUpdate(**request.get_json())
        update_teacher_data(
            tid,
            {k: v for k, v in payload.dict().items() if v is not None},
        )
        return jsonify({"success": True}), 200
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400
    except Exception as e:
        print(f"❌ Error in update_teacher_route: {e}")
        return jsonify({"success": False, "message": "Failed to update teacher"}), 500


@bp.route("/<tid>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")
def delete_teacher_route(tid):
    try:
        delete_teacher_data(tid)
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"❌ Error in delete_teacher_route: {e}")
        return jsonify({"success": False, "message": "Failed to delete teacher"}), 500


@bp.route("/<tid>/assign_classroom", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def assign_classroom_route(tid):
    cid = request.json.get("classroom_id")
    assign_classroom_to_teacher(tid, cid)
    return jsonify({"success": True}), 200


@bp.route("/<tid>/remove_classroom", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def remove_classroom_route(tid):
    cid = request.json.get("classroom_id")
    remove_classroom_from_teacher(tid, cid)
    return jsonify({"success": True}), 200


# -- Bulk Import (CSV) --
@bp.route("/import/csv", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def import_teachers_csv():
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "message": "CSV file required"}), 400
    result = import_entities_from_csv(f.read(), entity_type="teacher")
    return jsonify(result), 200 if result["success"] else 400


# -- (Optional) Bulk Export (CSV) --
@bp.route("/export/csv", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def export_teachers_csv():
    teachers = get_all_teachers()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "email", "phone", "role"])
    writer.writeheader()
    for t in teachers:
        writer.writerow({k: t.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    return(
        output.getvalue(),
        200,
        {
            "Content-Disposition": "attachment; filename=teachers.csv",
            "Content-type": "text/csv"
        }
    )
