from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "classrooms"


def create_classroom(data: dict):
    db = get_db()
    doc = {
        "name": data["name"],
        "code": data.get("code") or data["name"].replace(" ", "_").lower(),
        "teacher": data.get("teacher"),
        "student_ids": data.get("student_ids", []),
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
    doc = db[COLL].find_one({"_id": ObjectId(cid)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def update_classroom(cid: str, data: dict):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(cid)},
        {"$set": {**(data or {}), "updated_at": datetime.utcnow()}},
    )


def delete_classroom(cid: str):
    db = get_db()
    db[COLL].delete_one({"_id": ObjectId(cid)})


def add_students_to_classroom(classroom_id: str, student_ids: list):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(classroom_id)},
        {
            "$addToSet": {"student_ids": {"$each": student_ids}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )


def remove_students_from_classroom(classroom_id: str, student_ids: list):
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(classroom_id)},
        {
            "$pullAll": {"student_ids": student_ids},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )


def get_students_of_classroom(classroom_id: str):
    db = get_db()
    classroom = db[COLL].find_one(
        {"_id": ObjectId(classroom_id)},
        {"student_ids": 1},
    )
    return classroom.get("student_ids", []) if classroom else []
