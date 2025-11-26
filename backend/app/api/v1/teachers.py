from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from ...schemas.teacher_schema import TeacherCreate, TeacherUpdate
from ...services.teacher_service import (
    get_all_teachers,
    add_teacher,
    get_teacher_by_id,
    update_teacher_data,
    delete_teacher_data,
    assign_classroom_to_teacher,
    remove_classroom_from_teacher,
)
from ...services.import_service import import_entities_from_csv
from ...utils.auth import requires_roles
import csv
import io

bp = Blueprint("teachers", __name__)

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