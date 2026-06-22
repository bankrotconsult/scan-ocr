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


def _normalize_fio(person: str) -> str:
    if not re.fullmatch(r'[А-ЯЁа-яёA-Za-z\s\-]+', person.strip()):
        return person
    return re.sub(r'[А-ЯЁа-яёA-Za-z]+', lambda m: m.group(0).capitalize(), person)


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

    print(f"[SHEET] Читаем таблицу {sheet_id}...")
    creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(sheet_id).get_worksheet(0)
    rows = worksheet.get_all_values()
    print(f"[SHEET] Получено строк: {len(rows)}")

    case_to_fio: dict[str, str] = {}
    fio_to_cases: dict[str, list[str]] = {}
    skipped = 0

    for i, row in enumerate(rows):
        if len(row) < 2:
            skipped += 1
            continue

        fio_raw = row[0].strip()
        case_raw = row[1].strip()

        # Пропускаем заголовок (первая строка, если содержит не ФИО)
        if i == 0 and not re.search(r'[А-ЯЁа-яё]', fio_raw):
            print(f"[SHEET] Строка 0 выглядит как заголовок, пропускаем: {fio_raw}")
            skipped += 1
            continue

        fio = _normalize_fio(fio_raw)
        case = extract_case_number(case_raw)

        if not fio or case == "UNKNOWN":
            print(f"[SHEET] Пропускаем строку {i + 1}: fio={fio_raw!r}, case={case_raw!r}")
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
    print(f"[SHEET] Обработано: {len(fio_to_cases)} ФИО, {len(case_to_fio)} дел, пропущено: {skipped}")
    print(f"[SHEET] Записано в {cache_dir}")

    return {
        "fio_count": len(fio_to_cases),
        "case_count": len(case_to_fio),
        "skipped": skipped,
        "updated_at": updated_at,
    }
