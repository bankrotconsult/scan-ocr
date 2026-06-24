from src.stats.dto import StatIncrementDTO
from src.stats.models import ProcessingStat
from src.stats.repository import StatsRepository


class StatsService:
    def __init__(self, repository: StatsRepository):
        self.repository = repository

    async def increment(self, dto: StatIncrementDTO) -> None:
        await self.repository.increment(dto)

    async def get_stats(self) -> ProcessingStat | None:
        return await self.repository.get_or_create()
