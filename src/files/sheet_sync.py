import json
import os
import re
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from src.config.base import BaseConfig
from src.llm import extract_case_number

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
CASE_TO_FIO_FILE = "case_to_fio.json"
FIO_TO_CASES_FILE = "fio_to_cases.json"

# Per-tab config: (tab_name, fio_column_header, case_column_header)
_TABS = [
    ("сопровождение",     "Должник", "№ дела"),
    ("Завершение 2026",   "Должник", "№ дела"),
    ("Завершение 2025",   "Должник", "№ дела"),
    ("Освобождение 2026", "Должник", "№ дела"),
    ("ОСВОБОЖДЕНИЕ 2025", "реструктуризация", "процедуры после реструктуризации"),
]


def _normalize_fio(person: str) -> str:
    if not re.fullmatch(r'[А-ЯЁа-яёA-Za-z\s\-]+', person.strip()):
        return person
    return re.sub(r'[А-ЯЁа-яёA-Za-z]+', lambda m: m.group(0).capitalize(), person)


def _find_header(rows: list[list[str]], fio_name: str, case_name: str) -> tuple[int | None, int | None, int | None]:
    """Scan rows top-to-bottom; return (row_index, fio_col_idx, case_col_idx) or (None, None, None)."""
    for i, row in enumerate(rows):
        lower = [c.strip().lower() for c in row]
        if fio_name.lower() in lower and case_name.lower() in lower:
            return i, lower.index(fio_name.lower()), lower.index(case_name.lower())
    return None, None, None


def get_cache_dir() -> str:
    cache_dir = BaseConfig.SHEET_CACHE_DIR or "/app/cache"
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def load_case_to_fio() -> dict[str, str]:
    path = os.path.join(get_cache_dir(), CASE_TO_FIO_FILE)
    try:
        print(f"[CACHE] Загружаем {path}...")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print(f"[CACHE] Файл не найден: {path}, возвращаем пустой словарь")
        return {}


def load_fio_to_cases() -> dict[str, list[str]]:
    path = os.path.join(get_cache_dir(), FIO_TO_CASES_FILE)
    try:
        print(f"[CACHE] Загружаем {path}...")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print(f"[CACHE] Файл не найден: {path}, возвращаем пустой словарь")
        return {}


def sync_sheet() -> dict:
    sheet_id = BaseConfig.GOOGLE_SHEETS_ID
    creds_path = BaseConfig.GOOGLE_CREDENTIALS_PATH

    if not sheet_id:
        raise ValueError("GOOGLE_SHEETS_ID не задан в .env")
    if not os.path.exists(creds_path):
        raise ValueError(f"Файл credentials.json не найден: {creds_path}")

    print(f"[SHEET] Открываем таблицу {sheet_id}...")
    creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(sheet_id)

    case_to_fio: dict[str, str] = {}
    fio_to_cases: dict[str, list[str]] = {}
    skipped = 0
    total_rows = 0

    for tab_name, fio_col_name, case_col_name in _TABS:
        try:
            ws = spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            print(f"[SHEET] Вкладка не найдена: «{tab_name}», пропускаем")
            continue

        rows = ws.get_all_values()
        print(f"[SHEET] Вкладка «{tab_name}»: получено строк {len(rows)}")

        header_idx, fio_idx, case_idx = _find_header(rows, fio_col_name, case_col_name)
        if header_idx is None:
            print(f"[SHEET] Вкладка «{tab_name}»: заголовки «{fio_col_name}» / «{case_col_name}» не найдены, пропускаем")
            continue

        print(f"[SHEET] Вкладка «{tab_name}»: заголовок в строке {header_idx + 1}, колонки [{fio_idx}, {case_idx}]")

        for i, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            fio_raw = row[fio_idx].strip() if fio_idx < len(row) else ""
            case_raw = row[case_idx].strip() if case_idx < len(row) else ""

            if not fio_raw and not case_raw:
                continue

            total_rows += 1
            fio = _normalize_fio(fio_raw)
            case = extract_case_number(case_raw)

            if not fio or case == "UNKNOWN":
                print(f"[SHEET] «{tab_name}» строка {i}: пропускаем fio={fio_raw!r}, case={case_raw!r}")
                skipped += 1
                continue

            case_to_fio[case] = fio
            if fio not in fio_to_cases:
                fio_to_cases[fio] = []
            if case not in fio_to_cases[fio]:
                fio_to_cases[fio].append(case)

    cache_dir = get_cache_dir()
    c2f_path = os.path.join(cache_dir, CASE_TO_FIO_FILE)
    f2c_path = os.path.join(cache_dir, FIO_TO_CASES_FILE)

    with open(c2f_path, "w", encoding="utf-8") as f:
        json.dump(case_to_fio, f, ensure_ascii=False, indent=2)
    with open(f2c_path, "w", encoding="utf-8") as f:
        json.dump(fio_to_cases, f, ensure_ascii=False, indent=2)

    updated_at = datetime.now(timezone.utc).isoformat()
    print(f"[SHEET] Итого: {len(fio_to_cases)} ФИО, {len(case_to_fio)} дел, пропущено: {skipped}")
    print(f"[SHEET] Записано в {cache_dir}")

    return {
        "fio_count": len(fio_to_cases),
        "case_count": len(case_to_fio),
        "skipped": skipped,
        "updated_at": updated_at,
    }
