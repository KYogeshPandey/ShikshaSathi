from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional

class TeacherCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    email: EmailStr
    classroom_ids: Optional[List[str]] = []

class TeacherUpdate(BaseModel):
    name: Optional[str]
    classroom_ids: Optional[List[str]]
