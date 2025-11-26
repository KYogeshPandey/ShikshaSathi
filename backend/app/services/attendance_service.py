from ..models.attendance import (
    create_attendance,
    list_attendance,
    get_attendance,
    update_attendance,
    delete_attendance,
    aggregate_attendance_stats,
    bulk_upsert_attendance,
    get_attendance_daily_records,   # <-- add this model function
    export_attendance_csv_file      # <-- add this export model helper
)

def add_attendance(data: dict):
    data = data or {}
    return create_attendance(data)

def get_all_attendance(filter_params: dict | None = None):
    return list_attendance(filter_params or {})

def get_attendance_by_id(aid: str):
    return get_attendance(aid)

def update_attendance_data(aid: str, data: dict):
    data = data or {}
    update_attendance(aid, data)

def delete_attendance_data(aid: str):
    delete_attendance(aid)

def get_attendance_stats(
    date_from=None,
    date_to=None,
    classroom_id: str | None = None,
    student_id: str | None = None,
):
    return aggregate_attendance_stats(
        date_from=date_from,
        date_to=date_to,
        classroom_id=classroom_id,
        student_id=student_id
    )

def get_attendance_detail(
    classroom_id: str | None = None,
    student_id: str | None = None,
    date_from=None,
    date_to=None
):
    return get_attendance_daily_records(
        classroom_id=classroom_id,
        student_id=student_id,
        date_from=date_from,
        date_to=date_to
    )

def export_attendance_report(
    classroom_id: str | None = None,
    student_id: str | None = None,
    date_from=None,
    date_to=None,
    fmt="csv"
):
    # Returns filepath for CSV/JSON export
    return export_attendance_csv_file(
        classroom_id=classroom_id,
        student_id=student_id,
        date_from=date_from,
        date_to=date_to,
        fmt=fmt
    )

def save_bulk_attendance(records: list[dict], marked_by: str | None = None) -> int:
    if not records:
        return 0
    return bulk_upsert_attendance(records, marked_by=marked_by)
