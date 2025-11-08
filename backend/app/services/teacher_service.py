from app.models.teacher import (
    create_teacher, list_teachers, get_teacher,
    update_teacher, delete_teacher, assign_classroom, remove_classroom
)

def add_teacher(data: dict):
    return create_teacher(data)

def get_all_teachers():
    return list_teachers()

def get_teacher_by_id(tid: str):
    return get_teacher(tid)

def update_teacher_data(tid: str, data: dict):
    update_teacher(tid, data)

def delete_teacher_data(tid: str):
    delete_teacher(tid)

def assign_classroom_to_teacher(tid: str, cid: str):
    assign_classroom(tid, cid)

def remove_classroom_from_teacher(tid: str, cid: str):
    remove_classroom(tid, cid)
