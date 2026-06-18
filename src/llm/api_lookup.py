import asyncio

import httpx

from src.llm.normalizer import extract_case_number

_CASE_API_BASE_URL = "https://api.bankrotconsult.ru/deals"
_FIO_API_URL = "https://api.bankrotconsult.ru/deals/by-fio/"
_TIMEOUT = 15.0
_RETRY_DELAY = 120.0


def _log(direction: str, message: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}\n{direction}  {message}\n{sep}")


async def _safe_get(url: str, params: dict, label: str) -> httpx.Response | None:
    """GET with one retry after _RETRY_DELAY seconds on network/timeout errors."""
    for attempt in range(2):
        attempt_tag = f" [попытка {attempt + 1}/2]" if attempt > 0 else ""
        _log(">>>", f"{label}  →  GET {url}{attempt_tag}\n    params: {params}")
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
                resp = await client.get(
                    url, params=params, headers={"accept": "application/json"}
                )
            resp.raise_for_status()
            _log("<<<", f"{label}  ←  status={resp.status_code}\n    response: {resp.json()}")
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            if attempt == 0:
                _log(
                    "⟳⟳⟳",
                    f"{label}  сетевая ошибка, повтор через {int(_RETRY_DELAY)}s\n"
                    f"    {type(e).__name__}: {repr(e)}",
                )
                await asyncio.sleep(_RETRY_DELAY)
            else:
                _log("!!!", f"{label}  ПОВТОР ТОЖЕ УПАЛ: {type(e).__name__}: {repr(e)}")
                return None
        except Exception as e:
            _log("!!!", f"{label}  ERROR: {type(e).__name__}: {repr(e)}")
            return None
    return None


async def lookup_person_by_case(case_number: str) -> tuple[str | None, bool]:
    """
    Returns (person_name, found_in_db).
      found_in_db=True  — API вернул объект сделки (номер дела существует в базе).
      found_in_db=False — null/ошибка сети (файл → ручная проверка).
      person_name=None  — сделка найдена, но title пустой.
    case_number всегда приходит с кириллической А (нормализовано в extract_case_number).
    """
    url = f"{_CASE_API_BASE_URL}/by-case-number/{case_number}"
    resp = await _safe_get(url, {}, "CASE LOOKUP")
    if resp is None:
        return None, False

    data = resp.json()
    if not data or not isinstance(data, dict):
        _log("---", f"CASE LOOKUP  null-ответ для «{case_number}» — номера нет в базе")
        return None, False

    title = (data.get("title") or "").strip()
    if title:
        _log("✓✓✓", f"CASE LOOKUP  найдено: person=«{title}»")
        return title, True

    _log("---", "CASE LOOKUP  сделка найдена, но title пустой")
    return None, True


async def lookup_case_by_fio(person: str) -> tuple[str | None, str | None]:
    """
    Разбивает person на 3 части, ищет по ФИО.
    Returns (validated_case_number, cleaned_person) или (None, None).
    """
    parts = person.split()
    if len(parts) < 3:
        return None, None

    last_name   = parts[0].rstrip(",")
    first_name  = parts[1].rstrip(",")
    middle_name = parts[2].rstrip(",")
    cleaned_person = f"{last_name} {first_name} {middle_name}"

    resp = await _safe_get(
        _FIO_API_URL,
        {"last_name": last_name, "first_name": first_name, "middle_name": middle_name},
        "FIO LOOKUP",
    )
    if resp is None:
        return None, None

    data = resp.json()
    if not data or not isinstance(data, list):
        _log("---", f"FIO LOOKUP   пустой список для «{cleaned_person}»")
        return None, None

    if len(data) > 1:
        contact_ids = {d.get("bitrix_contact_id") for d in data}
        if len(contact_ids) > 1:
            _log(
                "---",
                f"FIO LOOKUP   {len(data)} сделок с разными bitrix_contact_id {contact_ids}"
                " — неоднозначно, пропускаем",
            )
            return None, None

    # Берём первую запись с непустым case_number (остальные могут иметь null)
    raw_case = next(
        (d.get("case_number") for d in data if d.get("case_number")),
        None,
    )
    if not raw_case:
        _log("---", f"FIO LOOKUP   сделки найдены, но во всех case_number пустой/null")
        return None, None

    validated = extract_case_number(raw_case)
    if validated != "UNKNOWN":
        _log("✓✓✓", f"FIO LOOKUP   найдено: case=«{validated}», person=«{cleaned_person}»")
        return validated, cleaned_person

    _log("---", f"FIO LOOKUP   сделка найдена, но case_number «{raw_case}» не подходит по формату")
    return None, None


async def lookup_case_by_lastname(last_name: str) -> tuple[str | None, str | None]:
    """Search by last name only (when only initials are available)."""
    resp = await _safe_get(
        _FIO_API_URL,
        {"last_name": last_name},
        "LASTNAME LOOKUP",
    )
    if resp is None:
        return None, None

    data = resp.json()
    if not data or not isinstance(data, list):
        _log("---", f"LASTNAME LOOKUP  пустой список для «{last_name}»")
        return None, None

    if len(data) > 1:
        contact_ids = {d.get("bitrix_contact_id") for d in data}
        if len(contact_ids) > 1:
            _log(
                "---",
                f"LASTNAME LOOKUP  {len(data)} сделок с разными contact_id {contact_ids}"
                " — неоднозначно, пропускаем",
            )
            return None, None

    raw_case = next((d.get("case_number") for d in data if d.get("case_number")), None)
    if not raw_case:
        _log("---", "LASTNAME LOOKUP  сделки найдены, но case_number пустой/null")
        return None, None

    validated = extract_case_number(raw_case)
    if validated == "UNKNOWN":
        _log("---", f"LASTNAME LOOKUP  case_number «{raw_case}» не подходит по формату")
        return None, None

    api_person = (data[0].get("title") or "").strip() or None
    _log("✓✓✓", f"LASTNAME LOOKUP  найдено: case=«{validated}», person=«{api_person}»")
    return validated, api_person
