from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "teachers"

def create_teacher(data: dict):
    db = get_db()
    doc = {
        "name": data["name"].strip(),
        "email": (data.get("email") or "").strip() or None,
        "phone": (data.get("phone") or "").strip() or None,
        "role": (data.get("role") or "teacher").strip(),
        # always store as list of str IDs
        "assigned_classrooms": data.get("classroom_ids", []),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def list_teachers(include_inactive: bool = False):
    """
    Default: only active teachers.
    """
    db = get_db()
    q = {}
    if not include_inactive:
        q["is_active"] = True
    result = []
    for t in db[COLL].find(q):
        t["_id"] = str(t["_id"])
        result.append(t)
    return result

def get_teacher(tid: str):
    db = get_db()
    try:
        oid = ObjectId(tid)
    except Exception:
        return None
    doc = db[COLL].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def update_teacher(tid: str, data: dict):
    if not data:
        return
    db = get_db()
    try:
        oid = ObjectId(tid)
    except Exception:
        return
    db[COLL].update_one(
        {"_id": oid},
        {"$set": {**data, "updated_at": datetime.utcnow()}},
    )

def delete_teacher(tid: str, hard: bool = False):
    """
    If hard=False (recommended), soft-delete by marking as 'is_active': False.
    For audit/history (reports/attendance), teachers should not be deleted from DB by default.
    """
    db = get_db()
    try:
        oid = ObjectId(tid)
    except Exception:
        return

    if hard:
        db[COLL].delete_one({"_id": oid})
    else:
        db[COLL].update_one(
            {"_id": oid},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        )

def assign_classroom(tid: str, cid: str):
    db = get_db()
    try:
        oid = ObjectId(tid)
    except Exception:
        return
    db[COLL].update_one(
        {"_id": oid},
        {
            "$addToSet": {"assigned_classrooms": cid},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )

def remove_classroom(tid: str, cid: str):
    db = get_db()
    try:
        oid = ObjectId(tid)
    except Exception:
        return
    db[COLL].update_one(
        {"_id": oid},
        {
            "$pull": {"assigned_classrooms": cid},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
