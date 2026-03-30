from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class Lead(BaseModel):
    id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    name: str = Field(..., description="Lead name")
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    linkedin_url: Optional[str] = None
    revenue_estimate: Optional[float] = None
    needs: Optional[str] = None
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
