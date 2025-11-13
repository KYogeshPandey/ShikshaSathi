from app.core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "attendance"

def create_attendance(data: dict):
    db = get_db()
    doc = {
        "student_id": data["student_id"],
        "classroom_id": data["classroom_id"],
        "date": data["date"],  # "YYYY-MM-DD"
        "status": "present" if data.get("present", True) else "absent",
        "marked_by": data.get("marked_by"),
        "remarks": data.get("remarks"),
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
            if v is not None:
                q[k] = v
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

def aggregate_attendance_stats(date_from=None, date_to=None, classroom_id=None, student_id=None):
    db = get_db()
    match = {}
    if classroom_id:
        match["classroom_id"] = classroom_id
    if student_id:
        match["student_id"] = student_id
    if date_from or date_to:
        match["date"] = {}
        if date_from:
            match["date"]["$gte"] = date_from
        if date_to:
            match["date"]["$lte"] = date_to
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "student_id": "$student_id",
                "classroom_id": "$classroom_id"
            },
            "total_days": {"$sum": 1},
            "present_days": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
            "absent_days": {"$sum": {"$cond": [{"$eq": ["$status", "absent"]}, 1, 0]}}
        }},
        {"$project": {
            "_id": 0,
            "student_id": "$_id.student_id",
            "classroom_id": "$_id.classroom_id",
            "total_days": 1,
            "present_days": 1,
            "absent_days": 1,
            "attendance_percent": {
                "$cond": [{"$eq": ["$total_days", 0]}, 0,
                    {"$multiply": [
                        {"$divide": ["$present_days", "$total_days"]}, 100
                    ]}]
            }
        }}
    ]
    return list(db[COLL].aggregate(pipeline))
