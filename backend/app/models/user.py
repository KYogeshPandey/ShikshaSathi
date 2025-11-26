from ..core.db import get_db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

COLL = "users"

def find_by_username(username: str):
    db = get_db()
    # Normalize input for safety
    u = (username or "").strip().lower()
    user = db[COLL].find_one({"username": u})
    if user:
        user["_id"] = str(user["_id"])
    return user

def create_user(username: str, email: str, password: str, role: str = "teacher"):
    db = get_db()
    
    # Normalize
    u = username.strip().lower()
    e = (email or "").strip().lower()
    r = (role or "teacher").strip()

    # Hash password
    hashed = generate_password_hash(password)

    doc = {
        "username": u,
        "email": e,
        "password_hash": hashed,
        "role": r,  # stored as simple string
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def verify_password(user: dict, password: str):
    if not user or "password_hash" not in user:
        return False
    return check_password_hash(user["password_hash"], password)
