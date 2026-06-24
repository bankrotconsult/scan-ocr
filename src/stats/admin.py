from sqladmin import ModelView

from src.stats.models import ProcessingStat


class ProcessingStatAdmin(ModelView, model=ProcessingStat):

    name = "Статистика"
    name_plural = "Статистика обработки"
    icon = "fa-solid fa-chart-bar"

    column_list = [
        ProcessingStat.id,
        ProcessingStat.total,
        ProcessingStat.success,
        ProcessingStat.no_case,
        ProcessingStat.bad_case,
        ProcessingStat.no_person,
        ProcessingStat.error,
        ProcessingStat.ocr_count,
        ProcessingStat.total_seconds,
    ]

    column_sortable_list = [ProcessingStat.id, ProcessingStat.total]

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True

    column_labels = {
        ProcessingStat.id: "ID",
        ProcessingStat.total: "Всего",
        ProcessingStat.success: "Успешно",
        ProcessingStat.no_case: "Без номера дела",
        ProcessingStat.bad_case: "Неизвестные номера",
        ProcessingStat.no_person: "Неизвестное ФИО",
        ProcessingStat.error: "Ошибки",
        ProcessingStat.ocr_count: "Кол-во OCR замеров",
        ProcessingStat.total_seconds: "Сумма секунд OCR",
    }
