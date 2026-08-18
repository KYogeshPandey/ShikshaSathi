from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    target_classroom_ids: List[str] = [] # Empty list means intended for specific students or generic

class AnnouncementResponse(BaseModel):
    id: str = Field(..., alias="_id")
    title: str
    content: str
    posted_by_name: str
    created_at: datetime
    
    class Config:
        populate_by_name = True
