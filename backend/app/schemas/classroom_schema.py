from pydantic import BaseModel, Field
from typing import Optional, List

class ClassroomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    code: Optional[str]
    teacher: Optional[str]
    student_ids: Optional[List[str]] = Field(default_factory=list)
