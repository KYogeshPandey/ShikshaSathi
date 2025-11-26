from ..core.db import get_db
from datetime import datetime

COLL = "audit_logs"

def create_log(event_type, user_id, meta: dict = None, entity_type=None, entity_id=None, description=None):
    db = get_db()
    doc = {
        "event_type": event_type,              # e.g. 'update', 'delete', 'login', 'export', etc.
        "user_id": str(user_id),
        "meta": meta or {},                    # extra contextual data (dict)
        "entity_type": entity_type,            # e.g. 'student', 'classroom'
        "entity_id": str(entity_id) if entity_id else None,
        "description": description,            # optional summary string
        "created_at": datetime.utcnow()
    }
    db[COLL].insert_one(doc)

def list_logs(filters: dict = None, limit=100, skip=0):
    db = get_db()
    q = {}
    if filters:
        for k, v in filters.items():
            if v:
                q[k] = v
    # Sort by latest first
    results = []
    for log in db[COLL].find(q).sort("created_at", -1).skip(skip).limit(limit):
        log["_id"] = str(log["_id"])
        results.append(log)
    return results

def find_log_by_id(log_id):
    db = get_db()
    from bson import ObjectId
    try:
        oid = ObjectId(log_id)
    except Exception:
        return None
    log = db[COLL].find_one({"_id": oid})
    if log:
        log["_id"] = str(log["_id"])
    return log

# Optional: (for compliance, not typical in ERP)
def delete_log(log_id):
    db = get_db()
    from bson import ObjectId
    try:
        oid = ObjectId(log_id)
    except Exception:
        return
    db[COLL].delete_one({"_id": oid})
