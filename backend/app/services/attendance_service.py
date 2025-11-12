def add_attendance(data: dict):
    from app.models.attendance import create_attendance
    return create_attendance(data)

def get_all_attendance(filter_params: dict = None):
    from app.models.attendance import list_attendance
    return list_attendance(filter_params)

def get_attendance_by_id(aid: str):
    from app.models.attendance import get_attendance
    return get_attendance(aid)

def update_attendance_data(aid: str, data: dict):
    from app.models.attendance import update_attendance
    update_attendance(aid, data)

def delete_attendance_data(aid: str):
    from app.models.attendance import delete_attendance
    delete_attendance(aid)
