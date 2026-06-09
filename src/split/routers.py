import os
import uuid
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from fastapi import File as FormFile
from fastapi.responses import FileResponse, HTMLResponse

from src.config.base import BaseConfig
from src.db.db import db_session
from src.files.dto import FileCreateDTO
from src.files.repository import FileRepository
from src.files.routers import _run_ocr
from src.files.schemas import FileResponseSchema
from src.files.service import FileService
from src.split.schemas import ProcessRequest, UploadResponse
from src.split.service import get_page_count, split_pdf

router = APIRouter(
    prefix="/split",
    tags=["Split"],
)

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "split.html")


@router.get("/", response_class=HTMLResponse)
async def split_page():
    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = FormFile(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    uploads_dir = BaseConfig.UPLOADS_DIR
    os.makedirs(uploads_dir, exist_ok=True)

    token = str(uuid.uuid4())
    file_path = os.path.join(uploads_dir, f"{token}.pdf")

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    page_count = get_page_count(file_path)
    return UploadResponse(token=token, page_count=page_count)


@router.get("/pdf/{token}")
async def serve_pdf(token: str):
    file_path = os.path.join(BaseConfig.UPLOADS_DIR, f"{token}.pdf")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/pdf")


@router.post("/process", response_model=list[FileResponseSchema])
async def process_split(body: ProcessRequest, background_tasks: BackgroundTasks):
    if not body.split_pages:
        raise HTTPException(status_code=400, detail="split_pages must not be empty")

    source_path = os.path.join(BaseConfig.UPLOADS_DIR, f"{body.token}.pdf")
    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Upload not found or already processed")

    total = get_page_count(source_path)
    if max(body.split_pages) > total:
        raise HTTPException(status_code=400, detail=f"Page number exceeds total pages ({total})")

    uploads_dir = BaseConfig.UPLOADS_DIR
    segment_paths = split_pdf(source_path, body.split_pages, uploads_dir)

    os.remove(source_path)

    records = []
    for seg_path in segment_paths:
        async with db_session() as s:
            record = await FileService(FileRepository(s)).add_one(
                FileCreateDTO(name=os.path.basename(seg_path), status="pending")
            )
        background_tasks.add_task(_run_ocr, record.id, seg_path)
        records.append(FileResponseSchema(**asdict(record)))

    return records
