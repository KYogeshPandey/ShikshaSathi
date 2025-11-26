from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "students"

def create_student(data: dict):
    db = get_db()
    doc = {
        "name": data["name"].strip(),
        "roll_no": data["roll_no"].strip(),
        "classroom_id": data["classroom_id"],
        "email": (data.get("email") or "").strip() or None,
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
    try:
        oid = ObjectId(sid)
    except Exception:
        return None

    doc = db[COLL].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def update_student(sid: str, data: dict):
    if not data:
        return
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception:
        return

    db[COLL].update_one(
        {"_id": oid},
        {"$set": {**data, "updated_at": datetime.utcnow()}},
    )

def delete_student(sid: str, hard: bool = False):
    """
    If hard=False (default), mark as inactive (soft delete).
    """
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception:
        return

    if hard:
        db[COLL].delete_one({"_id": oid})
    else:
        db[COLL].update_one(
            {"_id": oid},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        )

def bulk_move_students(student_ids: list[str], new_classroom_id: str):
    """
    Bulk class promotion/change helper.
    """
    if not student_ids or not new_classroom_id:
        return

    db = get_db()
    object_ids = []
    for sid in student_ids:
        try:
            object_ids.append(ObjectId(sid))
        except Exception:
            continue

    if not object_ids:
        return

    db[COLL].update_many(
        {"_id": {"$in": object_ids}},
        {
            "$set": {
                "classroom_id": new_classroom_id,
                "updated_at": datetime.utcnow(),
            }
        },
    )
