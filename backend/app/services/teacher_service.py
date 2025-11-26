from ..models.teacher import (
    create_teacher,
    list_teachers,
    get_teacher,
    update_teacher,
    delete_teacher,
    assign_classroom,
    remove_classroom,
)

def add_teacher(data: dict):
    data = data or {}
    return create_teacher(data)

def get_all_teachers(include_inactive: bool = False):
    """
    List all teachers. Default: active only.
    """
    return list_teachers(include_inactive=include_inactive)

def get_teacher_by_id(tid: str):
    return get_teacher(tid)

def update_teacher_data(tid: str, data: dict):
    data = data or {}
    update_teacher(tid, data)

def delete_teacher_data(tid: str, hard: bool = False):
    """
    Soft delete (is_active=False) by default to preserve history.
    """
    delete_teacher(tid, hard=hard)

def assign_classroom_to_teacher(tid: str, cid: str):
    assign_classroom(tid, cid)

def remove_classroom_from_teacher(tid: str, cid: str):
    remove_classroom(tid, cid)
