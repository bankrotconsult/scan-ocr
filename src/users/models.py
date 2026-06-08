from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.db import ModelBase


class User(ModelBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    password: Mapped[str] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)