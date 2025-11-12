from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import create_access_token
from pydantic import ValidationError
from app.schemas.auth_schema import RegisterSchema, LoginSchema
from app.services.auth_service import register_user, authenticate

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response, 200

    try:
        payload = LoginSchema(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    user = authenticate(payload.username, payload.password)
    if not user:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    token = create_access_token(
        identity=user["username"],
        additional_claims={"role": user["role"]}
    )
    return jsonify({
        "success": True,
        "message": "Login successful",
        "access_token": token,
        "user": {"username": user["username"], "role": user.get("role", "teacher")}
    }), 200
