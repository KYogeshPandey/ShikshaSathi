from app.models.attendance import (
    create_attendance, list_attendance, get_attendance, update_attendance, delete_attendance
)

def add_attendance(data: dict):
    return create_attendance(data)

def get_all_attendance(filter_params: dict = None):
    return list_attendance(filter_params)

def get_attendance_by_id(aid: str):
    return get_attendance(aid)

def update_attendance_data(aid: str, data: dict):
    update_attendance(aid, data)

def delete_attendance_data(aid: str):
    delete_attendance(aid)
