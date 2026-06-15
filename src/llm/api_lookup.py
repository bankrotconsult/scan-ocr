import httpx

from src.llm.normalizer import extract_case_number

_CASE_API_URL = "https://api.bk-dev.ru/deals/"
_FIO_API_URL = "https://api.bankrotconsult.ru/deals/by-fio/"
_TIMEOUT = 15.0


def _log(direction: str, message: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}\n{direction}  {message}\n{sep}")


async def lookup_person_by_case(case_number: str) -> str | None:
    """Returns person title from API by case number, or None on empty/error."""
    params = {"case_number": case_number}
    _log(">>>", f"CASE LOOKUP  →  GET {_CASE_API_URL}\n    params: {params}")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
            resp = await client.get(
                _CASE_API_URL,
                params=params,
                headers={"accept": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        _log("<<<", f"CASE LOOKUP  ←  status={resp.status_code}\n    response: {data}")
        if data and isinstance(data, list):
            title = data[0].get("title", "").strip()
            if title:
                _log("✓✓✓", f"CASE LOOKUP  person found: «{title}»")
                return title
        _log("---", "CASE LOOKUP  empty list — keeping OCR person")
    except Exception as e:
        _log("!!!", f"CASE LOOKUP  ERROR: {type(e).__name__}: {repr(e)}")
    return None


async def lookup_case_by_fio(person: str) -> str | None:
    """Splits person into 3 parts and searches by FIO. Returns validated case_number or None."""
    parts = person.split()
    if len(parts) < 3:
        return None
    last_name   = parts[0].rstrip(",")
    first_name  = parts[1].rstrip(",")
    middle_name = parts[2].rstrip(",")
    params = {"last_name": last_name, "first_name": first_name, "middle_name": middle_name}
    _log(">>>", f"FIO LOOKUP   →  GET {_FIO_API_URL}\n    params: {params}")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
            resp = await client.get(
                _FIO_API_URL,
                params=params,
                headers={"accept": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        _log("<<<", f"FIO LOOKUP   ←  status={resp.status_code}\n    response: {data}")
        if not data or not isinstance(data, list):
            _log("---", "FIO LOOKUP   empty list — keeping UNKNOWN case")
            return None

        if len(data) > 1:
            contact_ids = {d.get("bitrix_contact_id") for d in data}
            if len(contact_ids) > 1:
                _log("---", f"FIO LOOKUP   {len(data)} deals with different bitrix_contact_id {contact_ids} — ambiguous, skipping")
                return None

        raw_case = data[0].get("case_number", "").strip()
        validated = extract_case_number(raw_case)
        if validated != "UNKNOWN":
            _log("✓✓✓", f"FIO LOOKUP   case number found: «{validated}»")
            return validated
        _log("---", "FIO LOOKUP   deal found but case_number invalid — skipping")
    except Exception as e:
        _log("!!!", f"FIO LOOKUP   ERROR: {type(e).__name__}: {repr(e)}")
    return None
