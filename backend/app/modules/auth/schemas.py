from pydantic import BaseModel, EmailStr, Field


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organisation_name: str | None = None
    department: str | None = None
    phone_number: str | None = None


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
