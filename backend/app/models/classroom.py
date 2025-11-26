from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "classrooms"


def create_classroom(data: dict):
    db = get_db()

    name = data["name"].strip()
    standard = (data.get("standard") or "").strip() or None
    section = (data.get("section") or "").strip() or None
    label = (data.get("label") or name).strip() or name

    doc = {
        "name": name,
        "code": (data.get("code") or name)
        .strip()
        .replace(" ", "_")
        .lower(),
        "label": label,
        "standard": standard,
        "section": section,
        # keep as list of IDs / codes, not full objects
        "subjects": data.get("subjects", []),
        # optional teacher id / username
        "teacher": data.get("teacher"),
        # list of student_ids (ObjectId as string / roll_no etc.)
        "student_ids": data.get("student_ids", []),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)


def list_classrooms(include_inactive: bool = False):
    """
    Default: only active classrooms.
    """
    db = get_db()
    query: dict = {}
    if not include_inactive:
        query["is_active"] = True

    result = []
    for c in db[COLL].find(query):
        c["_id"] = str(c["_id"])
        result.append(c)
    return result


def get_classroom(cid: str):
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception:
        return None

    doc = db[COLL].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def update_classroom(cid: str, data: dict):
    if not data:
        return
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception:
        return

    db[COLL].update_one(
        {"_id": oid},
        {"$set": {**data, "updated_at": datetime.utcnow()}},
    )


def delete_classroom(cid: str, hard: bool = False):
    """
    If hard=False, soft delete (is_active=False).
    Soft delete is preferred in school ERPs so reports/history safe rahe. [web:40][web:158]
    """
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception:
        return

    if hard:
        db[COLL].delete_one({"_id": oid})
    else:
        db[COLL].update_one(
            {"_id": oid},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        )


def add_students_to_classroom(classroom_id: str, student_ids: list[str]):
    db = get_db()
    try:
        oid = ObjectId(classroom_id)
    except Exception:
        return

    if not student_ids:
        return

    db[COLL].update_one(
        {"_id": oid},
        {
            "$addToSet": {"student_ids": {"$each": student_ids}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )


def remove_students_from_classroom(classroom_id: str, student_ids: list[str]):
    db = get_db()
    try:
        oid = ObjectId(classroom_id)
    except Exception:
        return

    if not student_ids:
        return

    db[COLL].update_one(
        {"_id": oid},
        {
            "$pullAll": {"student_ids": student_ids},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )


def get_students_of_classroom(classroom_id: str):
    db = get_db()
    try:
        oid = ObjectId(classroom_id)
    except Exception:
        return []

    classroom = db[COLL].find_one(
        {"_id": oid},
        {"student_ids": 1},
    )
    return classroom.get("student_ids", []) if classroom else []
