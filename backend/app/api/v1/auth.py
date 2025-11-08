from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from pydantic import ValidationError
from app.schemas.auth_schema import RegisterSchema, LoginSchema
from app.services.auth_service import register_user, authenticate

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['POST'])
def register():
    try:
        payload = RegisterSchema(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    user_id, err = register_user(
        payload.username, payload.email, payload.password, payload.role
    )
    if err:
        return jsonify({"success": False, "message": err}), 409

    return jsonify({"success": True, "user_id": user_id}), 201

@bp.route('/login', methods=['POST'])
def login():
    try:
        payload = LoginSchema(**request.get_json())
    except ValidationError as e:
        return jsonify({"success": False, "errors": e.errors()}), 400

    user = authenticate(payload.username, payload.password)
    if not user:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    token = create_access_token(identity=user["username"])
    return jsonify({
        "success": True,
        "message": "Login successful",
        "access_token": token,
        "user": {"username": user["username"], "role": user.get("role", "teacher")}
    }), 200
