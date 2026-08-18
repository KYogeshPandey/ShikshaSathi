from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "announcements"

def create_announcement(data: dict):
    db = get_db()
    doc = {
        "title": data.get("title", "").strip(),
        "content": data.get("content", "").strip(),
        "posted_by_id": str(data.get("posted_by_id")),
        "posted_by_name": data.get("posted_by_name", "Teacher"),
        "target_classroom_ids": data.get("target_classroom_ids", []), # List of class IDs
        "is_global": False, 
        "created_at": datetime.utcnow(),
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)

def get_announcements_for_teacher(teacher_id: str):
    """Get announcements created BY this teacher"""
    db = get_db()
    cursor = db[COLL].find({"posted_by_id": str(teacher_id)}).sort("created_at", -1)
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results

def get_active_announcements():
    """Get all announcements (for dashboard display)"""
    db = get_db()
    # Limit to last 10 for efficiency
    cursor = db[COLL].find().sort("created_at", -1).limit(10)
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results
