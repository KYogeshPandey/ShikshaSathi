from werkzeug.security import check_password_hash
from ..core.db import get_db


def authenticate(username: str, password: str):
    """
    Validate username/password against MongoDB users collection.

    Returns:
        dict with user public data if valid, else None.
    """
    db = get_db()
    user = db.users.find_one({"username": username})

    if not user:
        return None

    if not check_password_hash(user.get("password_hash", ""), password):
        return None

    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "role": user.get("role", "student"),
        "email": user.get("email", ""),
        "name": user.get("name", user["username"]),
    }
