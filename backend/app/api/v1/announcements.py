from flask import Blueprint, request, jsonify
from ...models.announcement import create_announcement, get_announcements_for_teacher, get_active_announcements
from ...utils.auth import token_required

announcements_bp = Blueprint("announcements", __name__)

@announcements_bp.route("/send", methods=["POST"])
@token_required
def send_notice(current_user):
    data = request.json
    data["posted_by_id"] = current_user["id"]
    data["posted_by_name"] = current_user.get("name", "Teacher")
    
    try:
        notice_id = create_announcement(data)
        return jsonify({"message": "Notice sent", "id": notice_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@announcements_bp.route("/history", methods=["GET"])
@token_required
def get_history(current_user):
    notices = get_announcements_for_teacher(current_user["id"])
    return jsonify(notices), 200

@announcements_bp.route("/feed", methods=["GET"])
def get_feed():
    # Public feed for dashboard
    notices = get_active_announcements()
    return jsonify(notices), 200
