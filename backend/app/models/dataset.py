from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Dataset(Base):
    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(255))
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String))
    timeframe: Mapped[str] = mapped_column(String(10))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    file_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
