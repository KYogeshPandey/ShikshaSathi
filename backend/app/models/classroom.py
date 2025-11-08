from datetime import datetime
from app.core.db import get_db

COLL = "classrooms"

def create_classroom(data: dict):
    db = get_db()
    doc = {
        "name": data["name"],
        "code": data.get("code") or data["name"].replace(" ", "_").lower(),
        "teacher": data.get("teacher"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def list_classrooms():
    db = get_db()
    result = []
    for c in db[COLL].find({}, {"password_hash": 0}):
        c["_id"] = str(c["_id"])
        result.append(c)
    return result

def get_classroom(cid: str):
    db = get_db()
    from bson import ObjectId
    doc = db[COLL].find_one({"_id": ObjectId(cid)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def update_classroom(cid: str, data: dict):
    db = get_db()
    from bson import ObjectId
    db[COLL].update_one(
        {"_id": ObjectId(cid)},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )

def delete_classroom(cid: str):
    db = get_db()
    from bson import ObjectId
    db[COLL].delete_one({"_id": ObjectId(cid)})
