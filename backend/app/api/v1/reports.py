from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.utils.auth import requires_roles   # role-based security
from app.core.db import get_db
from bson import ObjectId

bp = Blueprint("attendance_report", __name__)

@bp.route("/report", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def attendance_report():
    student_id = request.args.get("student_id")
    classroom_id = request.args.get("classroom_id")
    month = request.args.get("month")  # "2025-11" type

    query = {}
    if student_id:
        query["student_id"] = student_id
    if classroom_id:
        query["classroom_id"] = classroom_id
    if month:
        query["date"] = {"$regex": f"^{month}"}

    db = get_db()
    records = list(db["attendance"].find(query))

    total = len(records)
    present = sum(1 for x in records if x.get("present"))
    absent = total - present
    per_day = [
        {
            "date": rec["date"],
            "present": rec["present"],
            "remarks": rec.get("remarks", "")
        }
        for rec in sorted(records, key=lambda x: x.get("date", ""))
    ]
    percent = (present / total) * 100 if total else 0

    result = {
        "student_id": student_id,
        "classroom_id": classroom_id,
        "month": month,
        "present": present,
        "absent": absent,
        "total": total,
        "attendance_percent": round(percent, 2),
        "details": per_day
    }
    return jsonify({"success": True, "data": result}), 200


@bp.route("/classroom_leaderboard", methods=["GET"])
@jwt_required()
@requires_roles("admin", "teacher")
def classroom_monthly_leaderboard():
    classroom_id = request.args.get("classroom_id")
    month = request.args.get("month")  # "2025-11" format

    if not classroom_id or not month:
        return jsonify({"success": False, "msg": "classroom_id and month required"}), 400

    db = get_db()
    try:
        classroom = db["classrooms"].find_one({"_id": ObjectId(classroom_id)})
    except Exception:
        return jsonify({"success": False, "msg": "Invalid classroom_id"}), 400

    if not classroom:
        return jsonify({"success": False, "msg": "Classroom not found"}), 404
    student_ids = classroom.get("student_ids", [])
    if not student_ids:
        return jsonify({"success": False, "msg": "No students in classroom"}), 404

    report = []
    for student_id in student_ids:
        q = {
            "student_id": student_id,
            "classroom_id": classroom_id,
            "date": {"$regex": f"^{month}"}
        }
        records = list(db["attendance"].find(q))
        total = len(records)
        present = sum(1 for x in records if x.get("present"))
        percent = (present / total * 100) if total else 0

        report.append({
            "student_id": student_id,
            "present": present,
            "total": total,
            "attendance_percent": round(percent, 2)
        })

    report.sort(key=lambda x: x["attendance_percent"], reverse=True)
    return jsonify({"success": True, "leaderboard": report}), 200
