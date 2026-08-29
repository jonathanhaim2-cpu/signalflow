from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    api_token: str
    tier: str
    is_admin: bool = False
    upgrade_requested_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    alerts_used_today: int = 0
    alerts_limit: int | None = 3
    alerts_remaining_today: int | None = 3
    channels_used: int = 0
    channel_limit: int | None = 1


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
