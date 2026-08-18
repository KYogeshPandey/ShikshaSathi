from ..models.student import (
    create_student,
    list_students,
    get_student,
    update_student,
    delete_student,
    bulk_move_students,
)


def add_student(data: dict):
    data = data or {}
    return create_student(data)


def get_students(classroom_id: str | None = None):
    """
    List students, optionally filtered by class.
    Defaults to listing only active students.
    """
    return list_students(classroom_id)


# --- FIX: Alias for compatibility with export/import APIs ---
def get_all_students(classroom_id: str | None = None):
    """
    Alias for get_students to fix ImportError.
    """
    return get_students(classroom_id)
# -----------------------------------------------------------


def get_student_by_id(sid: str):
    return get_student(sid)


def update_student_data(sid: str, data: dict):
    data = data or {}
    update_student(sid, data)


def delete_student_data(sid: str, hard: bool = False):
    """
    Soft delete by default (hard=False).
    """
    delete_student(sid, hard=hard)


def move_students_to_class(student_ids: list[str], new_classroom_id: str):
    """
    Bulk promotion / section change.
    """
    bulk_move_students(student_ids, new_classroom_id)
