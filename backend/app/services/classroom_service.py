from app.models.classroom import (
    create_classroom, list_classrooms, get_classroom,
    update_classroom, delete_classroom
)

def add_classroom(data: dict):
    return create_classroom(data)

def get_all_classrooms():
    return list_classrooms()

def get_classroom_by_id(cid: str):
    return get_classroom(cid)

def update_classroom_data(cid: str, data: dict):
    update_classroom(cid, data)

def delete_classroom_data(cid: str):
    delete_classroom(cid)
