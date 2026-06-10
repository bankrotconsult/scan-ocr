from src.files.dto import FileCreateDTO, FileResponseDTO
from src.files.repository import FileRepository


class FileService:
    def __init__(self, file_repo: FileRepository):
        self.file_repository = file_repo

    async def add_one(self, data: FileCreateDTO) -> FileResponseDTO:
        return await self.file_repository.add_one(data=data)

    async def get_one(self, data: dict) -> FileResponseDTO:
        return await self.file_repository.get_one(data=data)

    async def get_all(self) -> list[FileResponseDTO]:
        return await self.file_repository.get_all()

    async def update_ocr_result(
        self,
        file_id: int,
        context: str,
        status: str,
        name: str | None = None,
        org: str | None = None,
        person: str | None = None,
        context_blocks: str | None = None,
    ) -> None:
        await self.file_repository.update_ocr_result(
            file_id=file_id,
            context=context,
            status=status,
            name=name,
            org=org,
            person=person,
            context_blocks=context_blocks,
        )
