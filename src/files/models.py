from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.db import ModelBase


class File(ModelBase):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(256), nullable=True
    )

    org: Mapped[str] = mapped_column(
        String(128), nullable=True
    )

    person: Mapped[str] = mapped_column(
        String(256), nullable=True
    )

    context: Mapped[str] = mapped_column(
        Text, nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=True, default="pending"
    )
