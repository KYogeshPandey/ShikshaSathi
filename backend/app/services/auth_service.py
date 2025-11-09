from app.models.user import find_by_username, create_user, verify_password

def register_user(username: str, email: str, password: str, role: str):
    # Check if username is already taken
    existing = find_by_username(username)
    if existing:
        return None, "Username already exists"
    # Pass role to create_user (must be handled there too!)
    user_id = create_user(username, email, password, role)
    return user_id, None

def authenticate(username: str, password: str):
    user = find_by_username(username)
    if not user or not verify_password(user, password):
        return None
    # user["role"] should always exist if registration & create_user set it
    return user
