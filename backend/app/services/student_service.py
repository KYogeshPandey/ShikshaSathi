def add_student(data: dict):
    from app.models.student import create_student
    return create_student(data)

def get_students(classroom_id=None):
    from app.models.student import list_students
    return list_students(classroom_id)

def get_student_by_id(sid: str):
    from app.models.student import get_student
    return get_student(sid)

def update_student_data(sid: str, data: dict):
    from app.models.student import update_student
    update_student(sid, data)

def delete_student_data(sid: str):
    from app.models.student import delete_student
    delete_student(sid)
