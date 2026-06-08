from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.db import ModelBase


class File(ModelBase):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(128), nullable=True
    )

    context: Mapped[str] = mapped_column(
        String(128), nullable=True
    )
