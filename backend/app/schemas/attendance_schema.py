from pydantic import BaseModel, Field
from typing import Optional

class AttendanceCreate(BaseModel):
    student_id: str
    classroom_id: str
    date: str = Field(description="YYYY-MM-DD")
    present: bool
    marked_by: Optional[str]
    remarks: Optional[str]
