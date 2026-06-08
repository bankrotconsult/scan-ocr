from sqladmin import ModelView

from src.files.models import File


class FileAdmin(ModelView, model=File):

    name = "Файлы"
    name_plural = "Файлы"
    icon = "fa-solid fa-user"

    column_list = [
        File.id,
        File.name,
        File.context
    ]
    column_searchable_list = [File.name]
    column_sortable_list = [File.id]

    form_columns = [File.name, File.context, File.id]

    page_size = 20
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    column_labels = {
        File.id: "ID",
        File.name: "Имя файлы",
        File.context: "Контекст",
    }