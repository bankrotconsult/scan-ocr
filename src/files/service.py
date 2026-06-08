from src.files.dto import FileResponseDTO
from src.files.repository import FileRepository


class RegionService:
    def __init__(self, file_repo: FileRepository):
        self.file_repository = file_repo

    async def get_one(self, data: dict) -> FileResponseDTO:
        return await self.file_repository.get_one(data=data)

    async def get_all(self) -> list[FileResponseDTO]:
        return await self.file_repository.get_all()
