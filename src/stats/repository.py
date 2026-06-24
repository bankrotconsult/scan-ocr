from sqlalchemy import select, update

from src.db.db import Session
from src.stats.dto import StatIncrementDTO
from src.stats.models import ProcessingStat
from src.utils.repository import SQLAlchemyRepository

_VALID_OUTCOMES = {"success", "no_case", "bad_case", "no_person", "error"}


class StatsRepository(SQLAlchemyRepository):
    model = ProcessingStat

    def __init__(self, session: Session):
        self.session = session

    async def add_one(self, data: dict):
        obj = ProcessingStat(**data)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_or_create(self) -> ProcessingStat:
        result = await self.session.execute(select(ProcessingStat).limit(1))
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = ProcessingStat()
            self.session.add(stat)
            await self.session.flush()
        return stat

    async def increment(self, dto: StatIncrementDTO) -> None:
        stat = await self.get_or_create()

        col_name = dto.outcome if dto.outcome in _VALID_OUTCOMES else "error"

        values: dict = {
            "total": ProcessingStat.total + 1,
            col_name: getattr(ProcessingStat, col_name) + 1,
        }
        if dto.seconds is not None:
            values["total_seconds"] = ProcessingStat.total_seconds + dto.seconds
            values["ocr_count"] = ProcessingStat.ocr_count + 1

        await self.session.execute(
            update(ProcessingStat)
            .where(ProcessingStat.id == stat.id)
            .values(**values)
        )
