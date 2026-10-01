from pydantic import BaseModel
from typing import Literal

class UserCreate(BaseModel):
    email: str
    role: Literal["ADMIN", "USER"] = "USER"

class UserUpdate(BaseModel):
    is_active: bool

