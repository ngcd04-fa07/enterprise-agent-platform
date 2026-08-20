import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.membership import MembershipRole


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    organisation_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organisation_id: uuid.UUID
    role: MembershipRole


class AuthResponse(BaseModel):
    user: UserRead
    csrf_token: str
    active_organisation_id: uuid.UUID | None


class CurrentUserResponse(BaseModel):
    user: UserRead
    csrf_token: str
    active_organisation_id: uuid.UUID | None
    memberships: list[MembershipRead]
