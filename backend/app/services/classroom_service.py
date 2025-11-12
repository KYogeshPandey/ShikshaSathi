def add_classroom(data: dict):
    from app.models.classroom import create_classroom
    data.setdefault("student_ids", [])
    return create_classroom(data)

def get_all_classrooms():
    from app.models.classroom import list_classrooms
    return list_classrooms()

def get_classroom_by_id(cid: str):
    from app.models.classroom import get_classroom
    return get_classroom(cid)

def update_classroom_data(cid: str, data: dict):
    from app.models.classroom import update_classroom
    update_classroom(cid, data)

def delete_classroom_data(cid: str):
    from app.models.classroom import delete_classroom
    delete_classroom(cid)

def assign_students(classroom_id: str, student_ids: list):
    from app.models.classroom import add_students_to_classroom
    add_students_to_classroom(classroom_id, student_ids)

def unassign_students(classroom_id: str, student_ids: list):
    from app.models.classroom import remove_students_from_classroom
    remove_students_from_classroom(classroom_id, student_ids)

def list_students_in_classroom(classroom_id: str):
    from app.models.classroom import get_students_of_classroom
    return get_students_of_classroom(classroom_id)
