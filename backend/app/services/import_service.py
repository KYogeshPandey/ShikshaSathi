import csv
import io

from .student_service import add_student
from .teacher_service import add_teacher
from .classroom_service import add_classroom

# If you want to support Excel, you could use openpyxl or pandas.
# For now, basic CSV import shown.

def import_entities_from_csv(content, entity_type):
    """
    Generic CSV import handler.

    :param content: bytes object (file read as .read())
    :param entity_type: 'student', 'teacher', 'classroom'
    :return: {success, total, imported_count, failed_count, errors: [{row_no, error, row}]}
    """
    # Decode file
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    imported_count = 0
    errors = []

    for idx, row in enumerate(rows, start=2):  # start=2 for header offset in Excel
        try:
            if entity_type == "student":
                if not row.get("name") or not row.get("roll_no") or not row.get("classroom_id"):
                    raise ValueError("Missing required fields: name, roll_no, classroom_id")
                add_student({
                    "name": row["name"].strip(),
                    "roll_no": row["roll_no"].strip(),
                    "classroom_id": row["classroom_id"].strip(),
                    "email": row.get("email", "").strip()
                })
            elif entity_type == "teacher":
                if not row.get("name"):
                    raise ValueError("Missing required field: name")
                add_teacher({
                    "name": row["name"].strip(),
                    "email": row.get("email", "").strip(),
                    "phone": row.get("phone", "").strip(),
                    # Add other fields if your TeacherCreate schema requires them
                })
            elif entity_type == "classroom":
                if not row.get("name"):
                    raise ValueError("Missing required field: name")
                add_classroom({
                    "name": row["name"].strip(),
                    "standard": row.get("standard", "").strip(),
                    "section": row.get("section", "").strip(),
                    "label": row.get("label", "").strip(),
                    # Add other fields as needed
                })
            else:
                raise ValueError("Unsupported entity_type: " + str(entity_type))
            imported_count += 1
        except Exception as e:
            errors.append({
                "row_no": idx,
                "error": str(e),
                "row": row
            })

    result = {
        "success": imported_count == len(rows),
        "total": len(rows),
        "imported_count": imported_count,
        "failed_count": len(errors),
        "errors": errors
    }
    return result

# OPTIONAL: Excel import using pandas (install openpyxl and pandas for this)
# import pandas as pd
# def import_entities_from_excel(content, entity_type):
#     try:
#         df = pd.read_excel(io.BytesIO(content))
#         records = df.to_dict(orient="records")
#         # reuse import_entities_from_csv logic if you want
#         # or process similarly as above with error handling
#     except Exception as e:
#         return {"success": False, "error": str(e)}

