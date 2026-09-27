from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

# Trimmed first, so a whitespace-only value counts as empty.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

PASSWORD_MIN_LENGTH = 8
PASSWORD_RULE = "Password must be at least 8 characters and include at least one letter and one digit."


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class SignupRequest(BaseModel):
    # Staff roles are system defaults (ACC-R3); SCRUM-83 adds "attendee".
    role: Literal["event_organiser"]
    full_name: RequiredText
    email: EmailStr
    # Never trimmed: surrounding spaces are part of the password.
    password: str
    organisation_name: RequiredText
    phone_number: str | None = None

    @field_validator("password")
    @classmethod
    def _meets_password_rule(cls, password: str) -> str:
        # [Team decision] for SCRUM-80's "platform's password requirements".
        # A custom error type keeps the message free of Pydantic's
        # "Value error, " prefix, so the SPA can show it as-is.
        if (
            len(password) < PASSWORD_MIN_LENGTH
            or not any(char.isalpha() for char in password)
            or not any(char.isdigit() for char in password)
        ):
            raise PydanticCustomError("password_rule", PASSWORD_RULE)
        return password

    @field_validator("phone_number")
    @classmethod
    def _blank_phone_is_no_phone(cls, phone_number: str | None) -> str | None:
        # The form sends an unfilled optional field as "", which is not a number.
        if phone_number is None:
            return None
        return phone_number.strip() or None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class SetActiveRoleRequest(BaseModel):
    role: str = Field(min_length=1)


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organisation_name: str | None = None
    department: str | None = None
    phone_number: str | None = None
    roles: list[str] = Field(default_factory=list)


class UserResponse(BaseModel):
    id: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
    profile: ProfileResponse
