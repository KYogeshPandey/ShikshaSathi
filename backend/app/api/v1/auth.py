from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from ...services.auth_service import authenticate

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/v1/auth/login
    Body: { "username": "...", "password": "..." }
    """
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return (
            jsonify({"success": False, "message": "Username and password required"}),
            400,
        )

    user = authenticate(username, password)
    if not user:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    token = create_access_token(
        identity=user["id"],
        additional_claims={"role": user["role"]},
    )

    return (
        jsonify(
            {
                "success": True,
                "access_token": token,
                "user": user,
            }
        ),
        200,
    )
