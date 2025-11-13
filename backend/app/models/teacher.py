from app.core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "teachers"

def create_teacher(data: dict):
    db = get_db()
    doc = {
        "name": data["name"],
        "email": data.get("email"),
        "phone": data.get("phone"),
        "role": data.get("role", "teacher"),
        "assigned_classrooms": data.get("classroom_ids", []),  # always store as list of str IDs
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
        # add aur fields as per requirement
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def list_teachers():
    db = get_db()
    result = []
    for t in db[COLL].find({"is_active": True}):
        t["_id"] = str(t["_id"])
        result.append(t)
    return result

def get_teacher(tid: str):
    db = get_db()
    doc = db[COLL].find_one({"_id": ObjectId(tid)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def update_teacher(tid: str, data: dict):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(tid)},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )

def delete_teacher(tid: str):
    db = get_db()
    db[COLL].delete_one({"_id": ObjectId(tid)})

def assign_classroom(tid: str, cid: str):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(tid)},
        {"$addToSet": {"assigned_classrooms": cid}, "$set": {"updated_at": datetime.utcnow()}}
    )

def remove_classroom(tid: str, cid: str):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(tid)},
        {"$pull": {"assigned_classrooms": cid}, "$set": {"updated_at": datetime.utcnow()}}
    )
