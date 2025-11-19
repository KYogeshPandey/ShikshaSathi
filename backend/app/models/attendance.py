from ..core.db import get_db
from bson import ObjectId
from datetime import datetime

COLL = "attendance"


def _normalize_status(data: dict) -> str:
    """
    Ensure status is either 'present' or 'absent'.
    """
    status = (data.get("status") or "").lower()
    if status in {"present", "absent"}:
        return status
    # fallback to boolean 'present' field
    return "present" if data.get("present", True) else "absent"


def create_attendance(data: dict):
    db = get_db()
    status = _normalize_status(data)
    doc = {
        "student_id": str(data["student_id"]),
        "classroom_id": str(data["classroom_id"]),
        "date": str(data["date"]),  # "YYYY-MM-DD"
        "status": status,
        "marked_by": data.get("marked_by"),
        "remarks": data.get("remarks"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = db[COLL].insert_one(doc)
    return str(res.inserted_id)


def bulk_upsert_attendance(records: list[dict], marked_by: str | None = None) -> int:
    """
    For each record, upsert by (student_id, classroom_id, date).
    Invalid records (missing ids/date) ko skip karega, lekin
    clearly console mein print karega.
    """
    db = get_db()
    count = 0
    now = datetime.utcnow()

    print("DEBUG bulk_upsert_attendance got", len(records), "records")

    for i, data in enumerate(records):
        student_id = data.get("student_id")
        classroom_id = data.get("classroom_id")
        date = data.get("date")

        # Agar required fields nahi hain to skip + log
        if not student_id or not classroom_id or not date:
            print(f"SKIP[{i}] invalid record:", data)
            continue

        # Sab ko string bana dete hain (ObjectId / int ho to bhi)
        student_id = str(student_id)
        classroom_id = str(classroom_id)
        date = str(date)

        status = _normalize_status(data)

        update_doc = {
            "student_id": student_id,
            "classroom_id": classroom_id,
            "date": date,
            "status": status,
            "marked_by": marked_by or data.get("marked_by"),
            "remarks": data.get("remarks"),
            "updated_at": now,
        }

        db[COLL].update_one(
            {
                "student_id": student_id,
                "classroom_id": classroom_id,
                "date": date,
            },
            {
                "$set": update_doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

        # Yahan tak aa gaya matlab record valid tha
        count += 1

    print("DEBUG bulk_upsert_attendance saved", count, "records")
    return count


def list_attendance(filters: dict | None = None):
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
        {"$set": {**(data or {}), "updated_at": datetime.utcnow()}},
    )


def delete_attendance(aid: str):
    db = get_db()
    db[COLL].delete_one({"_id": ObjectId(aid)})


def aggregate_attendance_stats(
    date_from=None,
    date_to=None,
    classroom_id: str | None = None,
    student_id: str | None = None,
):
    db = get_db()
    match: dict = {}

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
        {
            "$group": {
                "_id": {
                    "student_id": "$student_id",
                    "classroom_id": "$classroom_id",
                },
                "total_days": {"$sum": 1},
                "present_days": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", "present"]}, 1, 0],
                    }
                },
                "absent_days": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", "absent"]}, 1, 0],
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "student_id": "$_id.student_id",
                "classroom_id": "$_id.classroom_id",
                "total_days": 1,
                "present_days": 1,
                "absent_days": 1,
                "attendance_percent": {
                    "$cond": [
                        {"$eq": ["$total_days", 0]},
                        0,
                        {
                            "$multiply": [
                                {"$divide": ["$present_days", "$total_days"]},
                                100,
                            ]
                        },
                    ]
                },
            }
        },
    ]

    return list(db[COLL].aggregate(pipeline))
