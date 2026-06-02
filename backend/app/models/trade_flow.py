from sqlalchemy import ForeignKey, SmallInteger, Numeric, String, CheckConstraint, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class TradeFlow(Base):
    __tablename__ = "trade_flows"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    reporter_id:  Mapped[str]        = mapped_column(ForeignKey("countries.id"), nullable=False)
    partner_id:   Mapped[str]        = mapped_column(ForeignKey("countries.id"), nullable=False)
    year:         Mapped[int]        = mapped_column(SmallInteger, nullable=False)
    quarter:      Mapped[int | None] = mapped_column(SmallInteger)
    direction:    Mapped[str]        = mapped_column(String, nullable=False)
    value_usd_m:  Mapped[float]      = mapped_column(Numeric(15, 2), nullable=False)
    share_pct:    Mapped[float|None] = mapped_column(Numeric(5, 2))
    source:       Mapped[str]        = mapped_column(String, default="UN Comtrade")
    fetched_at:   Mapped[str]        = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("direction IN ('export', 'import')", name="ck_direction"),
        CheckConstraint("reporter_id <> partner_id",         name="ck_no_self_trade"),
        UniqueConstraint("reporter_id", "partner_id", "year", "quarter", "direction"),
    )

    reporter = relationship("Country", foreign_keys=[reporter_id])
    partner  = relationship("Country", foreign_keys=[partner_id])
