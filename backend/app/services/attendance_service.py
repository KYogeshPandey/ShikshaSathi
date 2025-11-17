from ..models.attendance import (
    create_attendance,
    list_attendance,
    get_attendance,
    update_attendance,
    delete_attendance,
    aggregate_attendance_stats,
    bulk_upsert_attendance,
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
    return aggregate_attendance_stats(date_from, date_to, classroom_id, student_id)


def save_bulk_attendance(records: list[dict], marked_by: str | None = None) -> int:
    """
    Save or update multiple attendance records in bulk.

    records: list of dicts with keys:
        student_id, classroom_id, date, status ("present"/"absent"), optional remarks
    """
    if not records:
        return 0
    return bulk_upsert_attendance(records, marked_by=marked_by)
