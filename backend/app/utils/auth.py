from flask_jwt_extended import verify_jwt_in_request, get_jwt
from functools import wraps
from flask import jsonify

def requires_roles(*roles):
    """
    Decorator to protect route: Only users whose JWT roles match any of *roles can access.
    Usage: @requires_roles("admin", "teacher")
    """
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("role") not in roles:
                return jsonify({"success": False, "msg": "Unauthorized: Incorrect Role"}), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper
