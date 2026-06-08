from dataclasses import asdict

from sqlalchemy import select

from src.files.dto import FileResponseDTO, FileCreateDTO
from src.files.models import File
from src.utils.repository import SQLAlchemyRepository


class FileRepository(SQLAlchemyRepository):
    model = File

    def create_file_dto(self, file: File):
        return FileResponseDTO(
            id=file.id,
            name=file.name,
            context=file.context,
        )

    async def add_one(self, data: FileCreateDTO) -> FileResponseDTO:
        file = self.model(
            **asdict(data)
        )
        self.session.add(file)
        await self.session.flush()

        return self.create_file_dto(file=file)

    async def get_one(self, data: dict):
        file = await self.session.execute(select(self.model).filter_by(**data))
        file = file.scalars().one()

        return self.create_file_dto(file=file)

    async def get_all(self):
        files = await self.session.execute(select(self.model))
        files = files.scalars().all()
        result = []
        for file in files:
            file_dto = self.create_file_dto(file)
            result.append(file_dto)
        return result
