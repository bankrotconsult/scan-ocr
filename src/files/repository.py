from dataclasses import asdict

from sqlalchemy import select, update

from src.files.dto import FileResponseDTO, FileCreateDTO
from src.files.models import File
from src.utils.repository import SQLAlchemyRepository


class FileRepository(SQLAlchemyRepository):
    model = File

    def create_file_dto(self, file: File) -> FileResponseDTO:
        return FileResponseDTO(
            id=file.id,
            name=file.name,
            org=file.org,
            person=file.person,
            context=file.context,
            context_blocks=file.context_blocks,
            status=file.status,
        )

    async def add_one(self, data: FileCreateDTO) -> FileResponseDTO:
        file = self.model(**asdict(data))
        self.session.add(file)
        await self.session.flush()
        return self.create_file_dto(file=file)

    async def get_one(self, data: dict) -> FileResponseDTO:
        result = await self.session.execute(select(self.model).filter_by(**data))
        file = result.scalars().one()
        return self.create_file_dto(file=file)

    async def get_all(self) -> list[FileResponseDTO]:
        result = await self.session.execute(select(self.model))
        files = result.scalars().all()
        return [self.create_file_dto(f) for f in files]

    async def mark_all_pending_error(self) -> int:
        result = await self.session.execute(
            update(self.model).where(self.model.status == "pending").values(status="error")
        )
        return result.rowcount

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
        values: dict = {"context": context, "status": status}
        if name is not None:
            values["name"] = name
        if org is not None:
            values["org"] = org
        if person is not None:
            values["person"] = person
        if context_blocks is not None:
            values["context_blocks"] = context_blocks
        await self.session.execute(
            update(self.model).where(self.model.id == file_id).values(**values)
        )
