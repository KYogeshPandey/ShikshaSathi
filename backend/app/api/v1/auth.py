from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from ...services.auth_service import authenticate

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["POST"])
def login_route():
    """
    POST /api/v1/auth/login
    Body: { "username": "...", "password": "..." }
    """
    try:
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password")

        if not username or not password:
            return jsonify({
                "success": False,
                "message": "Username and password are required"
            }), 400

        # Authenticate via service
        user = authenticate(username, password)
        
        if not user:
            return jsonify({
                "success": False,
                "message": "Invalid credentials"
            }), 401

        # Create JWT
        token = create_access_token(
            identity=user["id"],
            additional_claims={"role": user["role"]}
        )

        return jsonify({
            "success": True,
            "access_token": token,
            "user": user
        }), 200

    except Exception as e:
        print(f"❌ Login Error: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500
