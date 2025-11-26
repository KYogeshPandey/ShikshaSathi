from ..models.subject import (
    create_subject,
    list_subjects,
    get_subject,
    update_subject,
    delete_subject,
)

def add_subject(data: dict) -> str:
    data = data or {}
    return create_subject(data)

def get_all_subjects(filters: dict | None = None):
    """
    Fetch subjects with optional filters:
    { "standard": "...", "classroom_id": "...", "code": "..." }
    """
    return list_subjects(filters or {})

def get_subject_by_id(sid: str):
    return get_subject(sid)

def update_subject_data(sid: str, data: dict):
    update_subject(sid, data or {})

def delete_subject_data(sid: str, hard: bool = False):
    """
    Soft delete by default.
    """
    delete_subject(sid, hard=hard)
