from datetime import datetime
from app.core.db import get_db
from bson import ObjectId

COLL = "attendance"

def create_attendance(data: dict):
    db = get_db()
    data['created_at'] = datetime.utcnow()
    data['updated_at'] = datetime.utcnow()
    res = db[COLL].insert_one(data)
    return str(res.inserted_id)

def list_attendance(filter_params=None):
    db = get_db()
    q = {}
    if filter_params:
        if filter_params.get("student_id"):
            q["student_id"] = filter_params["student_id"]
        if filter_params.get("classroom_id"):
            q["classroom_id"] = filter_params["classroom_id"]
        if filter_params.get("date"):
            q["date"] = filter_params["date"]
    result = []
    for a in db[COLL].find(q):
        a["_id"] = str(a["_id"])
        result.append(a)
    return result

def get_attendance(aid: str):
    db = get_db()
    doc = db[COLL].find_one({"_id": ObjectId(aid)})
    if doc:
        doc["_id"] = str(doc["_id"])
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
