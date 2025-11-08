from datetime import datetime
from app.core.db import get_db

COLL = "students"

def create_student(data: dict):
    db = get_db()
    doc = {
        "name": data["name"],
        "roll_no": data["roll_no"],
        "classroom_id": data["classroom_id"],
        "email": data.get("email"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def list_students(classroom_id=None):
    db = get_db()
    q = {"classroom_id": classroom_id} if classroom_id else {}
    result = []
    for stu in db[COLL].find(q, {"password_hash": 0}):
        stu["_id"] = str(stu["_id"])
        result.append(stu)
    return result
