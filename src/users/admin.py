from sqladmin import ModelView
from sqladmin.filters import BooleanFilter

from src.users.models import User


class UserAdmin(ModelView, model=User):
    column_filters = [BooleanFilter(User.is_active, "Активен")]

    name = "Администраторы"
    name_plural = "Администраторы"
    icon = "fa-solid fa-user"

    column_list = [
        User.id,
        User.username,
    ]
    column_searchable_list = [User.username]
    column_sortable_list = [User.id]

    form_columns = [User.username, User.password, User.is_active]

    page_size = 20
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    column_labels = {
        User.id: "ID",
        User.username: "Имя пользователя",
        User.password: "Пароль",
        User.is_active: "Активен",
    }