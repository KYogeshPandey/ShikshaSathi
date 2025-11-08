from app.models.student import create_student, list_students

def add_student(data: dict):
    sid = create_student(data)
    return sid

def get_students(classroom_id=None):
    return list_students(classroom_id)
