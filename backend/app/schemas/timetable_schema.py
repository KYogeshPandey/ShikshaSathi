from pydantic import BaseModel, Field
from typing import Optional, List

class TimetableCreate(BaseModel):
    teacher_id: Optional[str] = None # Optional because backend can infer from token
    classroom_id: str
    subject_id: str
    day: str = Field(..., description="Monday, Tuesday, etc.")
    start_time: str = Field(..., description="HH:MM format")
    end_time: str = Field(..., description="HH:MM format")

class TimetableEntryResponse(TimetableCreate):
    id: str = Field(..., alias="_id")
    teacher_name: Optional[str] = None
    classroom_name: Optional[str] = None
    subject_name: Optional[str] = None

    class Config:
        populate_by_name = True
