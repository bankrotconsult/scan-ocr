from dataclasses import dataclass


@dataclass
class UserCreateDTO:
    username: str
    password: str | None = None
    is_active: bool = False


@dataclass
class UserDTO:
    id: int
    username: str
    password: str | None = None
    is_active: bool = False
