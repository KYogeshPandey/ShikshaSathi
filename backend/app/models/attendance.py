from app.core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "attendance"

def create_attendance(data: dict):
    db = get_db()
    doc = {
        "student_id": data["student_id"],         # should be string or ObjectId
        "classroom_id": data["classroom_id"],
        "date": data["date"],                     # should be a string ISO, e.g. "2025-11-12"
        "status": data.get("status", "present"),  # present/absent/late or whatever enum you want
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def list_attendance(filters: dict = None):
    db = get_db()
    q = {}
    if filters:
        for k, v in filters.items():
            if v: q[k] = v
    result = []
    for a in db[COLL].find(q):
        a["_id"] = str(a["_id"])
        result.append(a)
    return result

def get_attendance(aid: str):
    db = get_db()
    doc = db[COLL].find_one({"_id": ObjectId(aid)})
    if doc: doc["_id"] = str(doc["_id"])
    return doc

def update_attendance(aid: str, data: dict):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(aid)},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )

def delete_attendance(aid: str):
    db = get_db()
    db[COLL].delete_one({"_id": ObjectId(aid)})
