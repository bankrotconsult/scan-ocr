import asyncio
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from fastapi import File as FormFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from src.config.base import BaseConfig
from src.db.db import db_session
from src.files.dto import FileCreateDTO
from src.files.repository import FileRepository
from src.files.schemas import FileResponseSchema, RenameFileRequest, ScanBadSelectedRequest
from src.files.service import FileService
from src.files.sheet_sync import load_case_to_fio, load_fio_to_cases, sync_sheet, get_cache_dir, CASE_TO_FIO_FILE, FIO_TO_CASES_FILE
from src.llm import (
    OllamaService,
    apply_org_rules,
    extract_case_number,
    extract_multi_entities,
    lookup_case_by_fio,
    lookup_case_by_lastname,
    lookup_person_by_case,
)
from src.ocr import PaddleOCRService
from src.stats.dto import StatIncrementDTO
from src.stats.repository import StatsRepository
from src.stats.service import StatsService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)

_NAMED_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "upload_named.html")
_SYNC_SHEET_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "sync_sheet.html")
_REVIEW_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "review.html")

_BAD_FOLDERS = {"Без номера дела", "Неизвестные номера дела"}


_PERSON_FALLBACK = "ФИО не найдены"
_CASE_FALLBACK = "№ -"

_DIR_CLIENT    = "Ответы"
_DIR_NO_CASE   = "Без номера дела"
_DIR_BAD_CASE  = "Неизвестные номера дела"
_DIR_NO_PERSON = "Неизвестное ФИО"


def _sanitize(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|\n\r\t]', '', value).strip()


def _make_filename(org: str, person: str, case: str) -> str:
    org_d = _sanitize(org)[:40].strip()
    person_d = _sanitize(person) if person != "UNKNOWN" else _PERSON_FALLBACK
    case_d = case.replace("/", "-").replace("\\", "-") if case != "UNKNOWN" else _CASE_FALLBACK
    return f"{org_d} | {person_d} | {case_d}"


def _normalize_fio(person: str) -> str:
    """Capitalize each word of FIO if it contains only letters, spaces, hyphens."""
    if person == "UNKNOWN":
        return person
    if not re.fullmatch(r'[А-ЯЁа-яёA-Za-z\s\-]+', person.strip()):
        return person
    return re.sub(r'[А-ЯЁа-яёA-Za-z]+', lambda m: m.group(0).capitalize(), person)


def _client_dest_dir(person: str, case: str, root: str) -> str:
    case_safe = case.replace("/", "-").replace("\\", "-")
    folder_client = _sanitize(f"{person} {case_safe}")
    year_m = re.search(r'[/\-](\d{4})$', case)
    if year_m:
        return os.path.join(root, year_m.group(1), folder_client, _DIR_CLIENT)
    return os.path.join(root, folder_client, _DIR_CLIENT)


_INITIAL_RE = re.compile(r'^(?:[А-ЯЁA-Z]\.){1,3}$')


def _extract_lastname_if_initials(person: str) -> str | None:
    """Return last name if person is 'Lastname I.O.' or 'Lastname I.' format."""
    words = person.strip().split()
    if len(words) < 2:
        return None
    lastname = words[0].rstrip(",")
    if len(lastname) < 2 or "." in lastname:
        return None
    initials = [w.rstrip(",") for w in words[1:]]
    if all(_INITIAL_RE.match(i) for i in initials):
        return lastname
    return None


def _split_fios(person: str) -> list[str]:
    """Extract ordered list of 3-word FIOs from a string (comma or space separated)."""
    candidates: list[str] = []
    for chunk in (p.strip() for p in person.split(",") if p.strip()):
        words = chunk.split()
        for i in range(0, len(words), 3):
            group = words[i:i + 3]
            if len(group) == 3:
                candidates.append(" ".join(group))
    seen: set[str] = set()
    result: list[str] = []
    for fio in candidates:
        if fio not in seen:
            seen.add(fio)
            result.append(fio)
    return result


def _unique_dest_path(dest_dir: str, base_name: str, ext: str) -> str:
    path = os.path.join(dest_dir, base_name + ext)
    counter = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"{base_name} ({counter}){ext}")
        counter += 1
    return path


@router.get("/named", response_class=HTMLResponse)
async def named_upload_page():
    with open(_NAMED_TEMPLATE_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.post("/named")
async def upload_named_files(files: list[UploadFile] = FormFile(...)):
    """Distribute pre-named files to correct folders without OCR/LLM."""
    root = BaseConfig.SCAN_FILES_DIR
    results = []

    for file in files:
        original_name = file.filename or ""
        stem = os.path.splitext(original_name)[0]
        parts = [p.strip() for p in stem.split("|")]

        if len(parts) < 3:
            results.append({"name": original_name, "status": "error", "dest": "Неверный формат имени (ожидается: Орг | ФИО | Номер дела)"})
            continue

        org = parts[0]
        person = _normalize_fio(parts[1])
        case_raw = parts[2]
        case = extract_case_number(case_raw)

        if not person or person == _PERSON_FALLBACK or case == "UNKNOWN":
            results.append({"name": original_name, "status": "error", "dest": "Не удалось определить ФИО или номер дела из имени файла"})
            continue

        uploads_dir = BaseConfig.UPLOADS_DIR
        os.makedirs(uploads_dir, exist_ok=True)
        ext = os.path.splitext(original_name)[1]
        temp_path = os.path.join(uploads_dir, f"{uuid.uuid4()}{ext}")
        contents = await file.read()
        with open(temp_path, "wb") as fh:
            fh.write(contents)

        try:
            dest_dir = _client_dest_dir(person, case, root)
            await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
            base_name = _make_filename(org, person, case)
            dest_path = await asyncio.to_thread(_unique_dest_path, dest_dir, base_name, ext)
            await asyncio.to_thread(shutil.move, temp_path, dest_path)
            results.append({"name": original_name, "status": "done", "dest": dest_path})
            try:
                async with db_session() as s:
                    await StatsService(StatsRepository(s)).increment(StatIncrementDTO(outcome="success"))
            except Exception as _se:
                print(f"[STATS] Ошибка записи: {_se}")
        except Exception as e:
            if await asyncio.to_thread(os.path.exists, temp_path):
                await asyncio.to_thread(os.remove, temp_path)
            results.append({"name": original_name, "status": "error", "dest": str(e)})

    return results


@router.get("/no-case-folder")
async def no_case_folder_info():
    """Check if 'Без номера дела' folder exists and return its Windows network path."""
    root = BaseConfig.SCAN_FILES_DIR
    folder_path = os.path.join(root, _DIR_NO_CASE)
    exists = await asyncio.to_thread(os.path.isdir, folder_path)
    share_root = (BaseConfig.SCAN_FILES_SHARE_URL or "").rstrip("/\\")
    windows_path = f"{share_root}/{_DIR_NO_CASE}" if share_root else None
    return {"exists": exists, "windows_path": windows_path}


@router.get("/sync-sheet", response_class=HTMLResponse)
async def sync_sheet_page():
    with open(_SYNC_SHEET_TEMPLATE_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/sync-sheet/status")
async def sync_sheet_status():
    """Return upload-busy flag and cache freshness info."""
    uploads_dir = BaseConfig.UPLOADS_DIR
    busy = False
    if await asyncio.to_thread(os.path.isdir, uploads_dir):
        entries = await asyncio.to_thread(os.listdir, uploads_dir)
        busy = any(
            os.path.isfile(os.path.join(uploads_dir, e)) for e in entries
        )

    cache_dir = get_cache_dir()
    c2f_path = os.path.join(cache_dir, CASE_TO_FIO_FILE)
    f2c_path = os.path.join(cache_dir, FIO_TO_CASES_FILE)
    c2f_exists = await asyncio.to_thread(os.path.exists, c2f_path)
    f2c_exists = await asyncio.to_thread(os.path.exists, f2c_path)
    cache_exists = c2f_exists and f2c_exists

    updated_at = None
    if cache_exists:
        mtime = await asyncio.to_thread(os.path.getmtime, c2f_path)
        from datetime import datetime, timezone
        updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return {"busy": busy, "cache_exists": cache_exists, "updated_at": updated_at}


@router.post("/sync-sheet")
async def do_sync_sheet():
    """Read Google Sheets table and rebuild local JSON caches."""
    try:
        result = await asyncio.to_thread(sync_sheet)
        return result
    except ValueError as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        import traceback
        print(f"[SHEET] Ошибка синхронизации: {e!r}\n{traceback.format_exc()}")
        return JSONResponse(
            content={"error": repr(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/search-cache")
async def search_cache(q: str = "", page: int = 1):
    """Search local cache by partial FIO or case number. Returns 10 results per page."""
    q_stripped = q.strip()
    if not q_stripped:
        return {"results": [], "total": 0, "page": 1, "pages": 0, "query": q}

    q_lower = q_stripped.lower()
    # Normalize case-number query: both / and - are equivalent
    q_case = q_stripped.replace("/", "-")

    fio_to_cases = load_fio_to_cases()
    case_to_fio = load_case_to_fio()

    matched: dict[str, list[str]] = {}

    for fio, cases in fio_to_cases.items():
        if q_lower in fio.lower():
            matched[fio] = cases

    for case, fio in case_to_fio.items():
        case_norm = case.replace("/", "-")
        if q_case.lower() in case_norm.lower():
            if fio not in matched:
                matched[fio] = fio_to_cases.get(fio, [case])

    results_all = [
        {"fio": fio, "cases": [c.replace("/", "-") for c in cases]}
        for fio, cases in sorted(matched.items())
    ]

    total = len(results_all)
    per_page = 10
    pages = max(1, (total + per_page - 1) // per_page) if total > 0 else 0
    page = max(1, min(page, pages)) if pages > 0 else 1
    start = (page - 1) * per_page

    return {
        "results": results_all[start : start + per_page],
        "total": total,
        "page": page,
        "pages": pages,
        "query": q_stripped,
    }


@router.post("/scan-bad")
async def scan_bad_folders(folder: str = _DIR_NO_CASE):
    """Scan a bad folder for properly-named files and move them to correct destinations."""
    if folder not in _BAD_FOLDERS:
        return JSONResponse(content={"error": "Invalid folder"}, status_code=400)
    root = BaseConfig.SCAN_FILES_DIR
    results = []

    scan_dirs = [
        os.path.join(root, folder),
    ]

    for scan_dir in scan_dirs:
        if not await asyncio.to_thread(os.path.isdir, scan_dir):
            continue
        filenames = await asyncio.to_thread(os.listdir, scan_dir)
        for filename in filenames:
            file_path = os.path.join(scan_dir, filename)
            if not await asyncio.to_thread(os.path.isfile, file_path):
                continue

            stem = os.path.splitext(filename)[0]
            parts = [p.strip() for p in stem.split("|")]
            if len(parts) < 3:
                continue

            org = parts[0]
            person = _normalize_fio(parts[1])
            case_raw = parts[2]
            case = extract_case_number(case_raw)

            if not person or person == _PERSON_FALLBACK or case == "UNKNOWN":
                continue

            ext = os.path.splitext(filename)[1]
            try:
                dest_dir = _client_dest_dir(person, case, root)
                await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
                base_name = _make_filename(org, person, case)
                dest_path = await asyncio.to_thread(_unique_dest_path, dest_dir, base_name, ext)
                await asyncio.to_thread(shutil.move, file_path, dest_path)
                results.append({"name": filename, "status": "done", "dest": dest_path})
                try:
                    async with db_session() as s:
                        await StatsService(StatsRepository(s)).increment(StatIncrementDTO(outcome="success"))
                except Exception as _se:
                    print(f"[STATS] Ошибка записи: {_se}")
            except Exception as e:
                results.append({"name": filename, "status": "error", "dest": str(e)})

    if not results:
        results.append({"name": "—", "status": "info", "dest": "Файлов в подходящем формате не найдено"})

    return results


@router.post("/scan-bad-selected")
async def scan_bad_selected(body: ScanBadSelectedRequest):
    """Move specific files from a bad folder to correct destinations by filename."""
    if body.folder not in _BAD_FOLDERS:
        return JSONResponse(content={"error": "Invalid folder"}, status_code=400)
    root = BaseConfig.SCAN_FILES_DIR
    results = []

    for filename in body.filenames:
        if "/" in filename or "\\" in filename or ".." in filename:
            results.append({"name": filename, "status": "error", "dest": "Недопустимое имя файла"})
            continue

        file_path = os.path.join(root, body.folder, filename)
        if not await asyncio.to_thread(os.path.isfile, file_path):
            results.append({"name": filename, "status": "error", "dest": "Файл не найден"})
            continue

        stem = os.path.splitext(filename)[0]
        parts = [p.strip() for p in stem.split("|")]
        if len(parts) < 3:
            results.append({"name": filename, "status": "error", "dest": "Неверный формат имени (ожидается: Орг | ФИО | Номер дела)"})
            continue

        org = parts[0]
        person = _normalize_fio(parts[1])
        case_raw = parts[2]
        case = extract_case_number(case_raw)

        if not person or person == _PERSON_FALLBACK or case == "UNKNOWN":
            results.append({"name": filename, "status": "error", "dest": "Не удалось определить ФИО или номер дела из имени файла"})
            continue

        ext = os.path.splitext(filename)[1]
        try:
            dest_dir = _client_dest_dir(person, case, root)
            await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
            base_name = _make_filename(org, person, case)
            dest_path = await asyncio.to_thread(_unique_dest_path, dest_dir, base_name, ext)
            await asyncio.to_thread(shutil.move, file_path, dest_path)
            results.append({"name": filename, "status": "done", "dest": dest_path})
            try:
                async with db_session() as s:
                    await StatsService(StatsRepository(s)).increment(StatIncrementDTO(outcome="success"))
            except Exception as _se:
                print(f"[STATS] Ошибка записи: {_se}")
        except Exception as e:
            results.append({"name": filename, "status": "error", "dest": str(e)})

    return results


_recovery_tasks: set[asyncio.Task] = set()


async def recover_uploads() -> None:
    uploads_dir = BaseConfig.UPLOADS_DIR
    if not os.path.isdir(uploads_dir):
        print(f"[RECOVERY] Папка uploads не найдена: {uploads_dir}", flush=True)
        return
    entries = [f for f in os.listdir(uploads_dir) if os.path.isfile(os.path.join(uploads_dir, f))]
    if not entries:
        print("[RECOVERY] Нет файлов в uploads/", flush=True)
        return

    print(f"[RECOVERY] Найдено файлов в uploads/: {len(entries)}", flush=True)
    recovered = 0
    files_to_recover: list[tuple[int, str]] = []

    for temp_name in entries:
        file_path = os.path.join(uploads_dir, temp_name)
        underscore = temp_name.find("_")

        file_id: int | None = None
        if underscore != -1:
            try:
                file_id = int(temp_name[:underscore])
            except ValueError:
                pass  # старый UUID-формат

        if file_id is None:
            original_name = temp_name[underscore + 1:] if underscore != -1 else temp_name
            print(f"[RECOVERY] Старый формат: {temp_name} → создаём запись (имя={original_name})", flush=True)
            async with db_session() as s:
                record = await FileService(FileRepository(s)).add_one(
                    FileCreateDTO(name=original_name, status="pending")
                )
            file_id = record.id
        else:
            try:
                async with db_session() as s:
                    record = await FileService(FileRepository(s)).get_one({"id": file_id})
            except Exception:
                print(f"[RECOVERY] Пропускаем {temp_name}: запись id={file_id} не найдена в БД", flush=True)
                continue

            if record.status == "done":
                print(f"[RECOVERY] {temp_name}: уже обработан, удаляем temp-файл", flush=True)
                await asyncio.to_thread(os.remove, file_path)
                continue

            print(f"[RECOVERY] Повторная обработка: {temp_name} (db id={file_id}, status={record.status})", flush=True)

        files_to_recover.append((file_id, file_path))
        recovered += 1

    print(f"[RECOVERY] Запущено повторно: {recovered} файлов", flush=True)

    if files_to_recover:
        async def _run_sequentially(items: list[tuple[int, str]]) -> None:
            for fid, fpath in items:
                await _run_ocr(fid, fpath)

        task = asyncio.create_task(_run_sequentially(files_to_recover))
        _recovery_tasks.add(task)
        task.add_done_callback(_recovery_tasks.discard)


async def _run_ocr_multi(
    file_id: int,
    file_path: str,
    org: str,
    text: str,
    blocks: list,
    entities: list[dict],
    t0: float,
) -> None:
    """Process a multi-entity document by creating one file copy per entity."""
    root = BaseConfig.SCAN_FILES_DIR
    ext = os.path.splitext(file_path)[1]
    _c2f = load_case_to_fio()
    _f2c = load_fio_to_cases()

    first_dest_path: str | None = None
    first_person: str = "UNKNOWN"
    any_copied = False

    for idx, entity in enumerate(entities):
        person: str = entity.get("person") or "UNKNOWN"
        case: str = entity.get("case") or "UNKNOWN"

        if case != "UNKNOWN":
            if case in _c2f:
                person = _c2f[case]
                print(f"[MULTI][CACHE] {case} → {person}")
                dest_dir = _client_dest_dir(person, case, root)
            else:
                print(f"[MULTI][CACHE] {case} не найден → API")
                api_person, found_in_db = await lookup_person_by_case(case)
                if not found_in_db:
                    dest_dir = os.path.join(root, _DIR_BAD_CASE)
                else:
                    if api_person:
                        person = api_person
                    if person == "UNKNOWN":
                        dest_dir = os.path.join(root, _DIR_NO_PERSON)
                    else:
                        dest_dir = _client_dest_dir(person, case, root)
        else:
            fios = _split_fios(person) if person != "UNKNOWN" else []
            cache_hit = False
            for fio in fios:
                if fio in _f2c:
                    cases = _f2c[fio]
                    if len(cases) == 1:
                        case = cases[0]
                        person = fio
                        dest_dir = _client_dest_dir(person, case, root)
                    else:
                        dest_dir = os.path.join(root, _DIR_NO_CASE)
                    cache_hit = True
                    break
            if not cache_hit:
                for fio in fios:
                    api_case, api_person = await lookup_case_by_fio(fio)
                    if api_case:
                        case = api_case
                        person = api_person
                        break
                if case != "UNKNOWN":
                    dest_dir = _client_dest_dir(person, case, root)
                else:
                    if person != "UNKNOWN":
                        lastname = _extract_lastname_if_initials(person)
                        if lastname:
                            api_case, api_person = await lookup_case_by_lastname(lastname)
                            if api_case:
                                case = api_case
                                if api_person:
                                    person = api_person
                    dest_dir = (
                        _client_dest_dir(person, case, root)
                        if case != "UNKNOWN"
                        else os.path.join(root, _DIR_NO_CASE)
                    )

        if dest_dir == os.path.join(root, _DIR_NO_CASE):
            _outcome = "no_case"
        elif dest_dir == os.path.join(root, _DIR_BAD_CASE):
            _outcome = "bad_case"
        elif dest_dir == os.path.join(root, _DIR_NO_PERSON):
            _outcome = "no_person"
        else:
            _outcome = "success"

        person = _normalize_fio(person)
        base_name = _make_filename(org, person, case)
        try:
            await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
            dest_path = await asyncio.to_thread(_unique_dest_path, dest_dir, base_name, ext)
            await asyncio.to_thread(shutil.copy2, file_path, dest_path)
            any_copied = True
            if first_dest_path is None:
                first_dest_path = dest_path
                first_person = person
            _seconds = time.monotonic() - t0 if idx == 0 else None
            try:
                async with db_session() as s:
                    await StatsService(StatsRepository(s)).increment(
                        StatIncrementDTO(outcome=_outcome, seconds=_seconds)
                    )
            except Exception as _se:
                print(f"[STATS] Ошибка записи: {_se}")
        except Exception as e:
            print(f"[MULTI] Ошибка копирования {person}/{case}: {e}")

    await asyncio.to_thread(os.remove, file_path)

    if any_copied and first_dest_path:
        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(
                file_id=file_id,
                context=text,
                context_blocks=json.dumps(blocks, ensure_ascii=False),
                status="done",
                name=os.path.basename(first_dest_path),
                org=org,
                person=first_person,
            )
    else:
        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(file_id, "", "error")


async def _run_ocr(file_id: int, file_path: str) -> None:
    _t0 = time.monotonic()
    try:
        blocks = await PaddleOCRService().predict_structured(file_path)
        text = "\n".join(b["text"] for b in blocks)
        raw_org, person, case_llm = await OllamaService().analyze_document(text, blocks)
        org = apply_org_rules(raw_org, text)
        case_from_llm = extract_case_number(case_llm) if case_llm != "UNKNOWN" else "UNKNOWN"
        # Verify LLM-found case number exists in source text (reject hallucinations)
        if case_from_llm != "UNKNOWN":
            body = re.match(r'[АA](\d{2}-\d+)', case_from_llm)
            if not body or not re.search(re.escape(body.group(1)), text):
                print(f"[CASE] LLM hallucinated '{case_from_llm}' — not found in text, ignoring")
                case_from_llm = "UNKNOWN"
        case = case_from_llm if case_from_llm != "UNKNOWN" else extract_case_number(text)

        multi = extract_multi_entities(org, text, blocks)
        if multi and len(multi) > 1:
            await _run_ocr_multi(file_id, file_path, org, text, blocks, multi, _t0)
            return

        root = BaseConfig.SCAN_FILES_DIR

        if case != "UNKNOWN":
            _c2f = load_case_to_fio()
            print(f"[CACHE] case_to_fio загружен: {len(_c2f)} записей")
            if case in _c2f:
                person = _c2f[case]
                print(f"[CACHE] Номер дела найден в кэше: {case} → {person}")
                dest_dir = _client_dest_dir(person, case, root)
            else:
                print(f"[CACHE] Номер дела не найден в кэше: {case} → обращаемся к API")
                api_person, found_in_db = await lookup_person_by_case(case)
                if not found_in_db:
                    dest_dir = os.path.join(root, _DIR_BAD_CASE)
                else:
                    if api_person:
                        person = api_person
                    if person == "UNKNOWN":
                        dest_dir = os.path.join(root, _DIR_NO_PERSON)
                    else:
                        dest_dir = _client_dest_dir(person, case, root)
        else:
            # Номера нет — пробуем найти по ФИО
            fios = _split_fios(person) if person != "UNKNOWN" else []
            _f2c = load_fio_to_cases()
            print(f"[CACHE] fio_to_cases загружен: {len(_f2c)} записей")
            cache_hit = False
            for fio in fios:
                if fio in _f2c:
                    cases = _f2c[fio]
                    if len(cases) == 1:
                        print(f"[CACHE] ФИО найдено в кэше: {fio} → дело {cases[0]}")
                        case = cases[0]
                        person = fio
                        dest_dir = _client_dest_dir(person, case, root)
                    else:
                        print(f"[CACHE] ФИО найдено в кэше: {fio} → несколько дел {cases}, папка 'Без номера дела'")
                        dest_dir = os.path.join(root, _DIR_NO_CASE)
                    cache_hit = True
                    break
                else:
                    print(f"[CACHE] ФИО не найдено в кэше: {fio}")
            if not cache_hit:
                print(f"[CACHE] Ни одно ФИО не найдено в кэше → обращаемся к API")
                for fio in fios:
                    api_case, api_person = await lookup_case_by_fio(fio)
                    if api_case:
                        case = api_case
                        person = api_person
                        break
                if case != "UNKNOWN":
                    dest_dir = _client_dest_dir(person, case, root)
                else:
                    # Fallback: try last name only if format is "Фамилия И.О."
                    if person != "UNKNOWN":
                        lastname = _extract_lastname_if_initials(person)
                        if lastname:
                            api_case, api_person = await lookup_case_by_lastname(lastname)
                            if api_case:
                                case = api_case
                                if api_person:
                                    person = api_person
                    if case != "UNKNOWN":
                        dest_dir = _client_dest_dir(person, case, root)
                    else:
                        dest_dir = os.path.join(root, _DIR_NO_CASE)

        if dest_dir == os.path.join(root, _DIR_NO_CASE):
            _stat_outcome = "no_case"
        elif dest_dir == os.path.join(root, _DIR_BAD_CASE):
            _stat_outcome = "bad_case"
        elif dest_dir == os.path.join(root, _DIR_NO_PERSON):
            _stat_outcome = "no_person"
        else:
            _stat_outcome = "success"

        person = _normalize_fio(person)
        base_name = _make_filename(org, person, case)
        ext = os.path.splitext(file_path)[1]
        await asyncio.to_thread(os.makedirs, dest_dir, exist_ok=True)
        dest_path = await asyncio.to_thread(_unique_dest_path, dest_dir, base_name, ext)
        await asyncio.to_thread(shutil.copy2, file_path, dest_path)
        await asyncio.to_thread(os.remove, file_path)

        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(
                file_id=file_id,
                context=text,
                context_blocks=json.dumps(blocks, ensure_ascii=False),
                status="done",
                name=os.path.basename(dest_path),
                org=org,
                person=person,
            )

        try:
            async with db_session() as s:
                await StatsService(StatsRepository(s)).increment(
                    StatIncrementDTO(outcome=_stat_outcome, seconds=time.monotonic() - _t0)
                )
        except Exception as _se:
            print(f"[STATS] Ошибка записи: {_se}")

    except Exception as e:
        print(f"OCR error for file {file_id}: {e}")
        if await asyncio.to_thread(os.path.exists, file_path):
            await asyncio.to_thread(os.remove, file_path)
        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(file_id, "", "error")
        try:
            async with db_session() as s:
                await StatsService(StatsRepository(s)).increment(
                    StatIncrementDTO(outcome="error", seconds=time.monotonic() - _t0)
                )
        except Exception as _se:
            print(f"[STATS] Ошибка записи: {_se}")


@router.post(
    "/upload",
    response_model=FileResponseSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = FormFile(...),
):
    try:
        uploads_dir = BaseConfig.UPLOADS_DIR
        os.makedirs(uploads_dir, exist_ok=True)

        async with db_session() as s:
            record = await FileService(FileRepository(s)).add_one(
                FileCreateDTO(name=file.filename, status="pending")
            )

        temp_name = f"{record.id}_{file.filename}"
        file_path = os.path.join(uploads_dir, temp_name)

        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        background_tasks.add_task(_run_ocr, record.id, file_path)

        return FileResponseSchema(**asdict(record))

    except Exception as e:
        print(str(e))
        return JSONResponse(
            content={"error": "server error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get(
    "/",
    response_model=list[FileResponseSchema],
)
async def get_files():
    try:
        async with db_session() as s:
            files = await FileService(FileRepository(s)).get_all()

        return [FileResponseSchema(**asdict(file)) for file in files]

    except Exception as e:
        print(str(e))
        return JSONResponse(
            content={"error": "server error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/review", response_class=HTMLResponse)
async def review_page():
    with open(_REVIEW_TEMPLATE_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/bad-folder-list")
async def bad_folder_list(folder: str = "Без номера дела"):
    if folder not in _BAD_FOLDERS:
        return JSONResponse(content={"error": "Invalid folder"}, status_code=400)
    root = BaseConfig.SCAN_FILES_DIR
    folder_path = os.path.join(root, folder)
    if not await asyncio.to_thread(os.path.isdir, folder_path):
        return {"files": []}
    entries = await asyncio.to_thread(os.listdir, folder_path)
    files = []
    for name in sorted(entries):
        full = os.path.join(folder_path, name)
        if not await asyncio.to_thread(os.path.isfile, full):
            continue
        stem, ext = os.path.splitext(name)
        parts = [p.strip() for p in stem.split("|")]
        org = parts[0] if len(parts) > 0 else ""
        fio = parts[1] if len(parts) > 1 else ""
        case = parts[2] if len(parts) > 2 else ""
        files.append({"name": name, "org": org, "fio": fio, "case": case, "ext": ext})
    return {"files": files}


@router.get("/serve-file")
async def serve_file(folder: str, name: str):
    if folder not in _BAD_FOLDERS:
        raise HTTPException(status_code=400, detail="Invalid folder")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    root = BaseConfig.SCAN_FILES_DIR
    file_path = os.path.join(root, folder, name)
    if not await asyncio.to_thread(os.path.isfile, file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@router.post("/rename-file")
async def rename_file_endpoint(body: RenameFileRequest):
    if body.folder not in _BAD_FOLDERS:
        raise HTTPException(status_code=400, detail="Invalid folder")
    if "/" in body.old_name or "\\" in body.old_name or ".." in body.old_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    root = BaseConfig.SCAN_FILES_DIR
    folder_path = os.path.join(root, body.folder)
    old_path = os.path.join(folder_path, body.old_name)
    if not await asyncio.to_thread(os.path.isfile, old_path):
        raise HTTPException(status_code=404, detail="File not found")
    ext = os.path.splitext(body.old_name)[1]
    org_s = _sanitize(body.org)[:40].strip()
    fio_s = _sanitize(body.fio).strip()
    case_s = _sanitize(body.case).strip()
    new_stem = f"{org_s} | {fio_s} | {case_s}"
    new_path = await asyncio.to_thread(_unique_dest_path, folder_path, new_stem, ext)
    await asyncio.to_thread(os.rename, old_path, new_path)
    return {"success": True, "new_name": os.path.basename(new_path)}


@router.get(
    "/{file_id}",
    response_model=FileResponseSchema,
)
async def get_file(file_id: int):
    try:
        async with db_session() as s:
            file = await FileService(FileRepository(s)).get_one({"id": file_id})

        return FileResponseSchema(**asdict(file))

    except Exception as e:
        print(str(e))
        return JSONResponse(
            content={"error": "not found"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
