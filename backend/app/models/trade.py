import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Trade(Base):
    __tablename__ = "trades"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id"))
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Numeric)
    price: Mapped[Decimal] = mapped_column(Numeric)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pnl: Mapped[Decimal] = mapped_column(Numeric, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
