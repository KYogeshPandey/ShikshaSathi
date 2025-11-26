from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from ...services.attendance_service import (
    save_bulk_attendance,
    get_attendance_stats,
    get_all_attendance,
    get_attendance_detail,   # NEW
    export_attendance_report # NEW
)
from ...utils.auth import requires_roles

bp = Blueprint("attendance", __name__)

@bp.route("/stats", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def get_stats_route():
    """
    Get aggregated attendance stats.
    Query params: classroom_id, from, to
    """
    try:
        classroom_id = request.args.get("classroom_id")
        date_from = request.args.get("from")
        date_to = request.args.get("to")

        stats = get_attendance_stats(
            date_from=date_from,
            date_to=date_to,
            classroom_id=classroom_id
        )
        return jsonify({"success": True, "data": stats}), 200
    except Exception as e:
        print(f"❌ Error in get_stats_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/detail", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def get_attendance_detail_route():
    """
    Returns daily/detailed attendance records for one class or one student.
    Query params: classroom_id, student_id, from, to
    """
    try:
        classroom_id = request.args.get("classroom_id")
        student_id = request.args.get("student_id")
        date_from = request.args.get("from")
        date_to = request.args.get("to")

        detail = get_attendance_detail(
            classroom_id=classroom_id,
            student_id=student_id,
            date_from=date_from,
            date_to=date_to,
        )
        return jsonify({"success": True, "data": detail}), 200
    except Exception as e:
        print(f"❌ Error in get_attendance_detail_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/export", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def export_attendance_route():
    """
    Download/export attendance table as CSV (for one class or student)
    """
    try:
        classroom_id = request.args.get("classroom_id")
        student_id = request.args.get("student_id")
        date_from = request.args.get("from")
        date_to = request.args.get("to")
        fmt = request.args.get("format", "json")  # "csv" or "json"

        file_path = export_attendance_report(
            classroom_id=classroom_id,
            student_id=student_id,
            date_from=date_from,
            date_to=date_to,
            fmt=fmt
        )
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        print(f"❌ Error in export_attendance_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/mystats", methods=["GET"])
@jwt_required()
def my_stats_route():
    """
    Get aggregated stats for the logged-in user (student).
    """
    try:
        user_id = get_jwt_identity()
        stats = get_attendance_stats(student_id=user_id)
        return jsonify({"success": True, "data": stats}), 200
    except Exception as e:
        print(f"❌ Error in my_stats_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

@bp.route("/manual", methods=["POST"])
@jwt_required()
@requires_roles("teacher", "admin")
def save_manual_attendance_route():
    """
    Bulk save attendance.
    Body: [ { "student_id": "...", "classroom_id": "...", "date": "...", "status": "..." } ]
    """
    try:
        data = request.get_json() or []
        if not isinstance(data, list) or not data:
            return jsonify({
                "success": False,
                "message": "Body must be a non-empty list"
            }), 400

        identity = get_jwt_identity()
        saved_count = save_bulk_attendance(data, marked_by=identity)

        return jsonify({
            "success": True,
            "message": "Attendance saved successfully",
            "saved": saved_count
        }), 200

    except Exception as e:
        print(f"❌ Error in save_manual_attendance_route: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
