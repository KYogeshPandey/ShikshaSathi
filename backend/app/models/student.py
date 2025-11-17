from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

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


def list_students(classroom_id: str | None = None):
    db = get_db()
    q: dict = {"is_active": True}
    if classroom_id:
        q["classroom_id"] = classroom_id

    result = []
    for s in db[COLL].find(q):
        s["_id"] = str(s["_id"])
        result.append(s)
    return result


def get_student(sid: str):
    db = get_db()
    doc = db[COLL].find_one({"_id": ObjectId(sid)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def update_student(sid: str, data: dict):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(sid)},
        {"$set": {**(data or {}), "updated_at": datetime.utcnow()}},
    )


def delete_student(sid: str):
    db = get_db()
    db[COLL].delete_one({"_id": ObjectId(sid)})
