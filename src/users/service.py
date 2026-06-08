from dataclasses import asdict

from src.users.dto import UserCreateDTO, UserDTO
from src.users.repository import UserRepository

class UserService:
    def __init__(
        self,
        admin_repo: UserRepository,
    ):
        self.admin_repo = admin_repo

    async def get_one(self, user_data: dict) -> UserDTO:
        return await self.admin_repo.get_one(user_data=user_data)

    async def add_one(self, user_data: UserCreateDTO) -> UserDTO:
        user_data = asdict(user_data)

        return await self.admin_repo.add_one(data=user_data)
