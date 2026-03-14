from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class Lead(BaseModel):
    first_name: Optional[str] = Field(None, example="Jane")
    last_name: Optional[str] = Field(None, example="Doe")
    email: EmailStr
    company: Optional[str] = Field(None, example="Acme Corp")
    title: Optional[str] = Field(None, example="Head of Sales")
    message: Optional[str] = Field(None, example="I'd love to connect about...")
