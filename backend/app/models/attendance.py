from ..core.db import get_db
from bson import ObjectId
from datetime import datetime
from pymongo import UpdateOne
import csv
import tempfile

COLL = "attendance"

def _normalize_status(data: dict) -> str:
    """
    Ensure status is either 'present' or 'absent'.
    """
    status = (data.get("status") or "").lower().strip()
    if status in {"present", "absent"}:
        return status
    # fallback to boolean 'present' field if status string missing
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
    Efficiently upsert records using bulk_write.
    """
    db = get_db()
    operations = []
    now = datetime.utcnow()
    for data in records:
        student_id = data.get("student_id")
        classroom_id = data.get("classroom_id")
        date = data.get("date")
        if not student_id or not classroom_id or not date:
            continue
        student_id = str(student_id)
        classroom_id = str(classroom_id)
        date = str(date)
        status = _normalize_status(data)
        update_doc = {
            "status": status,
            "marked_by": marked_by or data.get("marked_by"),
            "remarks": data.get("remarks"),
            "updated_at": now,
        }
        op = UpdateOne(
            {
                "student_id": student_id,
                "classroom_id": classroom_id,
                "date": date
            },
            {
                "$set": update_doc,
                "$setOnInsert": {"created_at": now}
            },
            upsert=True
        )
        operations.append(op)
    if operations:
        try:
            result = db[COLL].bulk_write(operations)
            return result.upserted_count + result.modified_count
        except Exception as e:
            print(f"Bulk write error: {e}")
            return 0
    return 0

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
    try:
        oid = ObjectId(aid)
    except Exception:
        return None
    doc = db[COLL].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def update_attendance(aid: str, data: dict):
    if not data:
        return
    db = get_db()
    try:
        oid = ObjectId(aid)
    except Exception:
        return
    db[COLL].update_one(
        {"_id": oid},
        {"$set": {**data, "updated_at": datetime.utcnow()}},
    )

def delete_attendance(aid: str):
    db = get_db()
    try:
        oid = ObjectId(aid)
    except Exception:
        return
    db[COLL].delete_one({"_id": oid})

def aggregate_attendance_stats(
    date_from=None,
    date_to=None,
    classroom_id: str | None = None,
    student_id: str | None = None,
):
    """
    Aggregation pipeline for analytics (aggregate by student+class)
    """
    db = get_db()
    match: dict = {}
    if classroom_id:
        match["classroom_id"] = str(classroom_id)
    if student_id:
        match["student_id"] = str(student_id)
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

def get_attendance_daily_records(
    classroom_id: str | None = None,
    student_id: str | None = None,
    date_from=None,
    date_to=None,
):
    """
    Return daily attendance records (detail table) for a given class or student within a date range.
    """
    db = get_db()
    q = {}
    if classroom_id:
        q["classroom_id"] = classroom_id
    if student_id:
        q["student_id"] = student_id
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    result = []
    for a in db[COLL].find(q).sort("date", 1):
        a["_id"] = str(a["_id"])
        result.append(a)
    return result

def export_attendance_csv_file(
    classroom_id: str | None = None,
    student_id: str | None = None,
    date_from=None,
    date_to=None,
    fmt="csv"
):
    """
    Export attendance table as CSV file and return the path.
    """
    records = get_attendance_daily_records(
        classroom_id=classroom_id,
        student_id=student_id,
        date_from=date_from,
        date_to=date_to
    )
    # Create temp CSV file
    fd, path = tempfile.mkstemp(suffix=".csv")
    fieldnames = ["date", "student_id", "classroom_id", "status", "marked_by", "remarks"]
    with open(path, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in fieldnames})
    return path
