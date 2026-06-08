import asyncio
import getpass

from src.users.dto import UserCreateDTO
from src.users.repository import UserRepository
from src.users.service import UserService
from src.db.db import db_session


async def create_admin():
    username = input("Username: ")

    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("❌ Passwords do not match")
        return

    async with db_session() as s:
        admin = await UserService(admin_repo=UserRepository(s)).add_one(
            UserCreateDTO(username=username, password=password, is_active=True)
        )

    print(f"✅ Admin '{admin.username}' created")


if __name__ == "__main__":
    asyncio.run(create_admin())
