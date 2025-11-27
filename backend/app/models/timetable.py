from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "timetable"

def create_timetable_entry(data: dict):
    db = get_db()
    # Validate required fields
    required = ["teacher_id", "classroom_id", "subject_id", "day", "start_time", "end_time"]
    for field in required:
        if not data.get(field):
            raise ValueError(f"Field {field} is required")

    doc = {
        "teacher_id": str(data["teacher_id"]),
        "classroom_id": str(data["classroom_id"]),
        "subject_id": str(data["subject_id"]),
        "day": data["day"].title(),  # Monday, Tuesday...
        "start_time": data["start_time"], # HH:MM format (24hr)
        "end_time": data["end_time"],     # HH:MM format
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def get_teacher_schedule(teacher_id: str):
    db = get_db()
    # Returns list sorted by Day then Start Time. 
    # Note: Sorting by Day string isn't perfect (Mon, Tue) but works for basic display. 
    # Ideally, map days to integers 0-6 for sorting in frontend.
    pipeline = [
        {"$match": {"teacher_id": str(teacher_id)}},
        {"$lookup": {
            "from": "classrooms",
            "let": {"cid": {"$toObjectId": "$classroom_id"}},
            "pipeline": [{"$match": {"$expr": {"$eq": ["$_id", "$$cid"]}}}],
            "as": "classroom"
        }},
        {"$lookup": {
            "from": "subjects",
            "let": {"sid": {"$toObjectId": "$subject_id"}},
            "pipeline": [{"$match": {"$expr": {"$eq": ["$_id", "$$sid"]}}}],
            "as": "subject"
        }},
        {"$unwind": {"path": "$classroom", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$subject", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"day": 1, "start_time": 1}}
    ]
    
    results = list(db[COLL].aggregate(pipeline))
    for r in results:
        r["_id"] = str(r["_id"])
    return results

def delete_timetable_entry(entry_id: str):
    db = get_db()
    try:
        oid = ObjectId(entry_id)
        db[COLL].delete_one({"_id": oid})
    except:
        pass
