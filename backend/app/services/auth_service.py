from ..models.user import find_by_username, verify_password

def authenticate(username: str, password: str):
    """
    Validate username/password using User model helpers.

    Returns:
        dict with user public data if valid, else None.
    """
    # Input safety
    u_str = (username or "").strip().lower()
    
    # 1. Find user via model (returns dict with string _id)
    user = find_by_username(u_str)
    if not user:
        return None

    # 2. Verify password via model
    if not verify_password(user, password):
        return None

    # 3. Return safe public dict
    return {
        "id": user["_id"],  # model already converted ObjectId -> str
        "username": user["username"],
        "role": user.get("role", "student"),
        "email": user.get("email", ""),
        "name": user.get("name", user["username"]),
    }
