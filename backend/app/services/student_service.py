from ..models.student import (
    create_student,
    list_students,
    get_student,
    update_student,
    delete_student,
)


def add_student(data: dict):
    data = data or {}
    return create_student(data)


def get_students(classroom_id: str | None = None):
    return list_students(classroom_id)


def get_student_by_id(sid: str):
    return get_student(sid)


def update_student_data(sid: str, data: dict):
    data = data or {}
    update_student(sid, data)


def delete_student_data(sid: str):
    delete_student(sid)
