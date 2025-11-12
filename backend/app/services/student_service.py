def add_student(data: dict):
    from app.models.student import create_student
    sid = create_student(data)
    return sid

def get_students(classroom_id=None):
    from app.models.student import list_students
    return list_students(classroom_id)
