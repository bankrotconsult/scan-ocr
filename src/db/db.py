from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config.base import BaseConfig


class ModelBase(DeclarativeBase):
    pass


engine = create_async_engine(
    BaseConfig.DATABASE_URL,
    echo=True
)
Session = async_sessionmaker(bind=engine)


@asynccontextmanager
async def db_session():
    session = Session()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()