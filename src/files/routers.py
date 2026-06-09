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
from src.llm import OllamaService
from src.ocr import PaddleOCRService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)


def _safe_filename(org: str, person: str) -> str:
    combined = f"{org}_{person}"
    safe = re.sub(r'[\\/:*?"<>|\n\r\t]', '', combined).strip()
    return safe if safe and safe != '_' else str(uuid.uuid4())


def _unique_dest_path(dest_dir: str, base_name: str, ext: str) -> str:
    path = os.path.join(dest_dir, base_name + ext)
    counter = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"{base_name} ({counter}){ext}")
        counter += 1
    return path


async def _run_ocr(file_id: int, file_path: str) -> None:
    try:
        text = await PaddleOCRService().predict(file_path)
        org, person = await OllamaService().analyze_document(text)

        base_name = _safe_filename(org, person)
        ext = os.path.splitext(file_path)[1]
        dest_dir = BaseConfig.SCAN_FILES_DIR
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = _unique_dest_path(dest_dir, base_name, ext)
        shutil.copy2(file_path, dest_path)
        os.remove(file_path)

        async with db_session() as s:
            await FileService(FileRepository(s)).update_ocr_result(
                file_id=file_id,
                context=text,
                status="done",
                name=os.path.basename(dest_path),
                org=org,
                person=person,
            )
    except Exception as e:
        print(f"OCR error for file {file_id}: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
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
