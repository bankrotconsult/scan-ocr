from sqlalchemy import select

from src.users.dto import UserDTO
from src.users.models import User
from src.utils.repository import SQLAlchemyRepository


class UserRepository(SQLAlchemyRepository):
    model = User

    def create_admin_dto(self, user) -> UserDTO:
        return UserDTO(
            id=user.id,
            username=user.username,
            password=user.password,
            is_active=user.is_active,
        )

    async def add_one(self, data: dict) -> UserDTO:
        user = self.model(**data)
        self.session.add(user)
        await self.session.flush()

        return self.create_admin_dto(user=user)

    async def get_one(self, user_data: dict) -> UserDTO:
        user = await self.session.execute(select(self.model).filter_by(**user_data))
        user = user.scalars().one()

        return self.create_admin_dto(user=user)