from sqlalchemy import Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.db.db import ModelBase


class ProcessingStat(ModelBase):
    __tablename__ = "processing_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    no_case: Mapped[int] = mapped_column(Integer, default=0)
    bad_case: Mapped[int] = mapped_column(Integer, default=0)
    no_person: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[int] = mapped_column(Integer, default=0)
    total_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    ocr_count: Mapped[int] = mapped_column(Integer, default=0)
