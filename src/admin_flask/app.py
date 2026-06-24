from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from src.users.admin import UserAdmin
from src.files.admin import FileAdmin
from src.stats.admin import ProcessingStatAdmin

from src.config.base import BaseConfig
from src.db.db import db_session, engine
from src.users.repository import UserRepository
from src.users.service import UserService


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        async with db_session() as s:
            user = await UserService(admin_repo=UserRepository(s)).get_one(
                user_data={"username": username, "password": password}
            )

            if user and user.is_active:
                request.session.update({"admin_user": user.username})
                return True

        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("admin_user") is not None


def init_admin(app):
    """
    init admin app
    """
    try:
        authentication_backend = AdminAuth(secret_key=BaseConfig.SECRET_KEY)

        admin = Admin(
            app=app,
            engine=engine,
            authentication_backend=authentication_backend,
            title="Админ панель",
            logo_url=None,
        )

        admin.add_view(UserAdmin)
        admin.add_view(FileAdmin)
        admin.add_view(ProcessingStatAdmin)

        return admin
    except Exception as e:
        print(e)
