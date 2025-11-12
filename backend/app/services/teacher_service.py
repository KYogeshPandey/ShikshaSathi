def add_teacher(data: dict):
    from app.models.teacher import create_teacher
    return create_teacher(data)

def get_all_teachers():
    from app.models.teacher import list_teachers
    return list_teachers()

def get_teacher_by_id(tid: str):
    from app.models.teacher import get_teacher
    return get_teacher(tid)

def update_teacher_data(tid: str, data: dict):
    from app.models.teacher import update_teacher
    update_teacher(tid, data)

def delete_teacher_data(tid: str):
    from app.models.teacher import delete_teacher
    delete_teacher(tid)

def assign_classroom_to_teacher(tid: str, cid: str):
    from app.models.teacher import assign_classroom
    assign_classroom(tid, cid)

def remove_classroom_from_teacher(tid: str, cid: str):
    from app.models.teacher import remove_classroom
    remove_classroom(tid, cid)
