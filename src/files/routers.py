import asyncio
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, UploadFile, status
from fastapi import File as FormFile
from fastapi.responses import HTMLResponse, JSONResponse

from src.config.base import BaseConfig
from src.db.db import db_session
from src.files.dto import FileCreateDTO
from src.files.repository import FileRepository
from src.files.schemas import FileResponseSchema
from src.files.service import FileService
from src.files.sheet_sync import load_case_to_fio, load_fio_to_cases, sync_sheet, get_cache_dir, CASE_TO_FIO_FILE, FIO_TO_CASES_FILE
from src.llm import (
    OllamaService,
    apply_org_rules,
    extract_case_number,
    lookup_case_by_fio,
    lookup_case_by_lastname,
    lookup_person_by_case,
)
from src.ocr import PaddleOCRService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)

_NAMED_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "upload_named.html")
_SYNC_SHEET_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "sync_sheet.html")


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
        print(f"[SHEET] Ошибка синхронизации: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post("/scan-bad")
async def scan_bad_folders():
    """Scan bad folders for properly-named files and move them to correct destinations."""
    root = BaseConfig.SCAN_FILES_DIR
    results = []

    scan_dirs = [
        os.path.join(root, _DIR_NO_CASE),
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
            except Exception as e:
                results.append({"name": filename, "status": "error", "dest": str(e)})

    if not results:
        results.append({"name": "—", "status": "info", "dest": "Файлов в подходящем формате не найдено"})

    return results


async def _run_ocr(file_id: int, file_path: str) -> None:
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
    except Exception as e:
        print(f"OCR error for file {file_id}: {e}")
        if await asyncio.to_thread(os.path.exists, file_path):
            await asyncio.to_thread(os.remove, file_path)
        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(file_id, "", "error")


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

        temp_name = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(uploads_dir, temp_name)

        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        async with db_session() as s:
            record = await FileService(FileRepository(s)).add_one(
                FileCreateDTO(name=file.filename, status="pending")
            )

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
