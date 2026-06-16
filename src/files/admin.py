from sqladmin import ModelView

from src.files.models import File


class FileAdmin(ModelView, model=File):

    name = "Файлы"
    name_plural = "Файлы"
    icon = "fa-solid fa-user"

    column_list = [
        File.id,
        File.name,
        File.org,
        File.person,
        File.status,
        File.context,
    ]
    column_searchable_list = [File.name, File.org, File.person]
    column_sortable_list = [File.id, File.org, File.person]

    form_columns = [File.name, File.org, File.person, File.context, File.id]

    page_size = 20
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    column_labels = {
        File.id: "ID",
        File.name: "Имя файла",
        File.org: "Организация",
        File.person: "Субъект (ФИО)",
        File.status: "Статус",
        File.context: "Контекст",
    }