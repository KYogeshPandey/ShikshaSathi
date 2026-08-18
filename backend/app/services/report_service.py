import tempfile
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from ..core.db import get_db

def generate_attendance_pdf_report(student_id=None, classroom_id=None, month=None):
    """
    Generate and save a temp PDF attendance report for one student or whole class for a month.
    Returns file path.
    """
    db = get_db()
    query = {}
    title = "Attendance Report"
    if student_id:
        query["student_id"] = student_id
        title = f"Attendance Report: Student {student_id}"
    if classroom_id:
        query["classroom_id"] = classroom_id
        title = f"Attendance Report: Class {classroom_id}" if not student_id else title
    if month:
        query["date"] = {"$regex": f"^{month}"}
        title = f"{title} ({month})"

    records = list(db["attendance"].find(query))
    summary = {
        "present": sum(1 for rec in records if rec.get("status") == "present"),
        "total": len(records)
    }
    percent = (summary["present"] / summary["total"] * 100) if summary["total"] else 0

    # Generate PDF
    temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    cnv = canvas.Canvas(temp_path, pagesize=letter)
    width, height = letter
    y = height - 50

    cnv.setFont("Helvetica-Bold", 16)
    cnv.drawString(50, y, title)
    y -= 32

    cnv.setFont("Helvetica", 12)
    cnv.drawString(50, y, f"Total: {summary['total']}")
    cnv.drawString(180, y, f"Present: {summary['present']}")
    cnv.drawString(320, y, f"Attendance %: {round(percent,2)} %")
    y -= 24

    cnv.setFont("Helvetica-Bold", 12)
    cnv.drawString(50, y, "Date")
    cnv.drawString(130, y, "Status")
    cnv.drawString(210, y, "Remarks")
    y -= 18
    cnv.setFont("Helvetica", 11)
    for rec in sorted(records, key=lambda r: r.get("date", "")):
        if y < 60:   # new page if bottom reached
            cnv.showPage()
            y = height - 50
        cnv.drawString(50, y, str(rec.get("date", "")))
        cnv.drawString(130, y, str(rec.get("status", "")))
        cnv.drawString(210, y, str(rec.get("remarks", ""))[:60])
        y -= 16

    cnv.save()
    return temp_path
