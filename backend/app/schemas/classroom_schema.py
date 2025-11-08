from pydantic import BaseModel, Field
from typing import Optional

class ClassroomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    code: Optional[str]
    teacher: Optional[str]
