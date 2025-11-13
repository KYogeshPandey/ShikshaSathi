from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class StudentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    roll_no: str = Field(min_length=1, max_length=20)
    classroom_id: str
    email: Optional[EmailStr]
