from pydantic import BaseModel
from typing import Literal, Optional


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    role: Literal["ADMIN", "USER"] = "USER"
    password: Optional[str] = None


class UserUpdate(BaseModel):
    is_active: bool

