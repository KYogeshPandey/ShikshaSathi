from ..core.db import get_db
from bson import ObjectId
from datetime import datetime
from typing import Optional, List

COLL = "subjects"

def create_subject(data: dict) -> str:
    """
    Minimal required field: name
    Optional: code, standard, description, subject_type, is_elective, classroom_ids
    """
    db = get_db()

    name = data["name"].strip()
    # Auto-generate code if not provided
    code = (data.get("code") or name).strip().replace(" ", "_").lower()

    doc = {
        "name": name,
        "code": code,
        "standard": (data.get("standard") or "").strip() or None,
        "description": (data.get("description") or "").strip() or None,
        "subject_type": (data.get("subject_type") or "").strip() or None,
        "is_elective": bool(data.get("is_elective", False)),
        # list of classroom_ids (string ObjectIds) this subject is mapped to
        "classroom_ids": data.get("classroom_ids", []),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True,
    }

    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)


def list_subjects(filters: Optional[dict] = None) -> List[dict]:
    db = get_db()
    q = {"is_active": True}

    if filters:
        # allow filtering by standard, classroom_id, code
        standard = filters.get("standard")
        if standard:
            q["standard"] = standard

        classroom_id = filters.get("classroom_id")
        if classroom_id:
            # MongoDB automatically matches if 'classroom_id' exists inside the 'classroom_ids' array
            q["classroom_ids"] = classroom_id

        code = filters.get("code")
        if code:
            q["code"] = code

    result = []
    for s in db[COLL].find(q):
        s["_id"] = str(s["_id"])
        result.append(s)
    return result


def get_subject(sid: str) -> Optional[dict]:
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception:
        return None

    doc = db[COLL].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def update_subject(sid: str, data: dict) -> None:
    if not data:
        return
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception:
        return

    # FIX: Remove _id from data if it exists to prevent immutable field error
    if "_id" in data:
        del data["_id"]

    payload = {**data, "updated_at": datetime.utcnow()}
    
    db[COLL].update_one(
        {"_id": oid}, 
        {"$set": payload}
    )


def delete_subject(sid: str, hard: bool = False) -> None:
    """
    If hard=False, just mark as inactive.
    """
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception:
        return

    if hard:
        db[COLL].delete_one({"_id": oid})
    else:
        db[COLL].update_one(
            {"_id": oid},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        )
