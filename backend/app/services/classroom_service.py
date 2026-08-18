from ..models.classroom import (
    create_classroom,
    list_classrooms,
    get_classroom,
    update_classroom,
    delete_classroom,
    add_students_to_classroom,
    remove_students_from_classroom,
    get_students_of_classroom,
)

def add_classroom(data: dict):
    data = data or {}
    data.setdefault("student_ids", [])
    return create_classroom(data)

def get_all_classrooms(include_inactive: bool = False):
    """
    Get list of classrooms.
    include_inactive=False by default (only active classes).
    """
    return list_classrooms(include_inactive=include_inactive)

def get_classroom_by_id(cid: str):
    return get_classroom(cid)

def update_classroom_data(cid: str, data: dict):
    data = data or {}
    update_classroom(cid, data)

def delete_classroom_data(cid: str, hard: bool = False):
    """
    Default soft delete (hard=False).
    """
    delete_classroom(cid, hard=hard)

def assign_students(classroom_id: str, student_ids: list):
    add_students_to_classroom(classroom_id, student_ids)

def unassign_students(classroom_id: str, student_ids: list):
    remove_students_from_classroom(classroom_id, student_ids)

def list_students_in_classroom(classroom_id: str):
    return get_students_of_classroom(classroom_id)
