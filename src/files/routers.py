from dataclasses import asdict

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from src.db.db import db_session
from src.files.repository import FileRepository
from src.files.schemas import FileResponseSchema
from src.files.service import FileService


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)


@router.get(
    "/",
    response_model=list[FileResponseSchema]
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