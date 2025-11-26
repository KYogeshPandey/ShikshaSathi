from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ...services.audit_log_service import get_logs, get_log_by_id, log_event, remove_log
from ...utils.auth import requires_roles

bp = Blueprint("logs", __name__)

@bp.route("/", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def list_logs_route():
    """
    Query params: user_id, event_type, entity_type, entity_id, skip, limit
    """
    filters = {
        "user_id": request.args.get("user_id"),
        "event_type": request.args.get("event_type"),
        "entity_type": request.args.get("entity_type"),
        "entity_id": request.args.get("entity_id")
    }
    filters = {k: v for k, v in filters.items() if v}
    skip = int(request.args.get("skip", 0))
    limit = int(request.args.get("limit", 100))
    logs = get_logs(filters, limit=limit, skip=skip)
    return jsonify({"success": True, "data": logs}), 200

@bp.route("/<log_id>", methods=["GET"])
@jwt_required()
@requires_roles("admin")
def get_log_route(log_id):
    log = get_log_by_id(log_id)
    if not log:
        return jsonify({"success": False, "message": "Log not found"}), 404
    return jsonify({"success": True, "data": log}), 200

# Optionally allow admin to remove old logs if needed:
@bp.route("/<log_id>", methods=["DELETE"])
@jwt_required()
@requires_roles("admin")
def delete_log_route(log_id):
    remove_log(log_id)
    return jsonify({"success": True}), 200

# Optionally: create logs via POST (not usually public API)
@bp.route("/", methods=["POST"])
@jwt_required()
@requires_roles("admin")
def add_log_route():
    data = request.get_json() or {}
    event_type = data.get("event_type")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    description = data.get("description")
    meta = data.get("meta")
    user_id = get_jwt_identity()
    log_event(event_type, user_id, meta=meta, entity_type=entity_type, entity_id=entity_id, description=description)
    return jsonify({"success": True}), 201
