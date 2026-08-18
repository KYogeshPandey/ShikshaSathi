from ..models.audit_log import create_log, list_logs, find_log_by_id, delete_log

def log_event(event_type, user_id, meta=None, entity_type=None, entity_id=None, description=None):
    """
    Write a single audit event.
    """
    return create_log(
        event_type=event_type,
        user_id=user_id,
        meta=meta or {},
        entity_type=entity_type,
        entity_id=entity_id,
        description=description
    )

def get_logs(filters=None, limit=100, skip=0):
    return list_logs(filters or {}, limit=limit, skip=skip)

def get_log_by_id(log_id):
    return find_log_by_id(log_id)

def remove_log(log_id):
    return delete_log(log_id)
