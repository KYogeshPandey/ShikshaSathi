from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from functools import wraps
from flask import jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# --- Password Utilities ---
def hash_password(password):
    return generate_password_hash(password)

def verify_password(hash, password):
    return check_password_hash(hash, password)


# --- Decorators ---
def requires_roles(*roles):
    """
    Decorator to protect route: Only users whose JWT roles match any of *roles can access.
    Usage: @requires_roles("admin", "teacher")
    """
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            try:
                verify_jwt_in_request()
                claims = get_jwt()
                if claims.get("role") not in roles:
                    return jsonify({"success": False, "msg": "Unauthorized: Incorrect Role"}), 403
                return fn(*args, **kwargs)
            except Exception as e:
                return jsonify({"success": False, "msg": str(e)}), 401
        return decorator
    return wrapper


# ✅ Compatibility Wrapper for 'token_required'
# Yeh wahi kaam karega jo naye routes expect kar rahe hain
def token_required(fn):
    @wraps(fn)
    def decorator(*args, **kwargs):
        try:
            verify_jwt_in_request()
            # Hum token se user identity (e.g., user_id or payload) nikalte hain
            current_user_identity = get_jwt_identity()
            claims = get_jwt()
            
            # Naye routes expect karte hain ki 'current_user' object pass ho
            # Hum ek dictionary bana dete hain jo user data contain kare
            current_user = {
                "id": current_user_identity, # usually string ID
                "role": claims.get("role"),
                "name": claims.get("name", "User") # Optional
            }
            
            return fn(current_user, *args, **kwargs)
        except Exception as e:
            return jsonify({"success": False, "msg": "Token is invalid or missing", "error": str(e)}), 401
    return decorator
