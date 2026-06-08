from abc import ABC, abstractmethod

from src.db.db import Session


class AbstractRepository(ABC):
    @abstractmethod
    def __init__(self, session: Session):
        raise NotImplementedError

    @abstractmethod
    async def add_one(self, data: dict):
        raise NotImplementedError


class SQLAlchemyRepository(AbstractRepository):
    model = None

    def __init__(self, session: Session):
        self.session = session