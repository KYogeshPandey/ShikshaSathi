from flask import Blueprint, request, jsonify
from ...models.timetable import create_timetable_entry, get_teacher_schedule, delete_timetable_entry
from ...utils.auth import token_required # Assuming you have a middleware

timetable_bp = Blueprint("timetable", __name__)

@timetable_bp.route("/", methods=["POST"])
@token_required
def add_entry(current_user):
    # Only Admin usually sets timetable, but allowing teachers for prototype
    data = request.json
    # If teacher is adding for themselves
    if "teacher_id" not in data:
        data["teacher_id"] = current_user["id"] 
    
    try:
        entry_id = create_timetable_entry(data)
        return jsonify({"message": "Entry added", "id": entry_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@timetable_bp.route("/my-schedule", methods=["GET"])
@token_required
def get_my_schedule(current_user):
    # Fetch schedule for the logged-in teacher
    schedule = get_teacher_schedule(current_user["id"])
    return jsonify(schedule), 200

@timetable_bp.route("/<entry_id>", methods=["DELETE"])
@token_required
def remove_entry(current_user, entry_id):
    delete_timetable_entry(entry_id)
    return jsonify({"message": "Entry deleted"}), 200
