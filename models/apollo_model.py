from pydantic import BaseModel, Field


class FindLeadsRequest(BaseModel):
    prompt: str = Field(..., example="Find 10 SaaS CTOs in London")
