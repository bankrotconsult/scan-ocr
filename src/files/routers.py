import asyncio
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, UploadFile, status
from fastapi import File as FormFile
from fastapi.responses import JSONResponse

from src.config.base import BaseConfig
from src.db.db import db_session
from src.files.dto import FileCreateDTO
from src.files.repository import FileRepository
from src.files.schemas import FileResponseSchema
from src.files.service import FileService
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
            # Всегда проверяем номер дела через основной сервис
            api_person, found_in_db = await lookup_person_by_case(case)
            if not found_in_db:
                # Номер есть в документе, но в базе не найден — ручная проверка
                dest_dir = os.path.join(root, _DIR_BAD_CASE)
            else:
                if api_person:
                    person = api_person
                if person == "UNKNOWN":
                    # Сделка в базе есть, но имя не определить
                    dest_dir = os.path.join(root, _DIR_NO_PERSON)
                else:
                    dest_dir = _client_dest_dir(person, case, root)
        else:
            # Номера нет — пробуем найти по ФИО (перебираем каждое найденное ФИО)
            fios = _split_fios(person) if person != "UNKNOWN" else []
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
