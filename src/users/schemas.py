from pydantic import BaseModel


class UserCreateSchema(BaseModel):
    username: str
    password: str | None
    is_active: bool = False


class UserSchema(BaseModel):
    id: int
    username: str
    password: str | None
    is_active: bool = False


class LoginSchema(BaseModel):
    username: str
    password: str
