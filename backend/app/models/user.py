from ..core.db import get_db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

COLL = "users"


def find_by_username(username: str):
    db = get_db()
    return db[COLL].find_one({"username": username})


def create_user(username: str, email: str, password: str, role: str = "teacher"):
    db = get_db()
    hashed = generate_password_hash(password)
    doc = {
        "username": username,
        "email": email,
        "password_hash": hashed,
        "role": role,  # role string stored in db!
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)


def verify_password(user: dict, password: str):
    return check_password_hash(user["password_hash"], password)
