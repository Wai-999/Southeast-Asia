from sqlalchemy import ForeignKey, SmallInteger, Numeric, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class IndicatorValue(Base):
    __tablename__ = "indicator_values"

    id:           Mapped[int]         = mapped_column(primary_key=True)
    country_id:   Mapped[str]         = mapped_column(ForeignKey("countries.id"), nullable=False)
    indicator_id: Mapped[int]         = mapped_column(ForeignKey("indicators.id"), nullable=False)
    year:         Mapped[int]         = mapped_column(SmallInteger, nullable=False)
    quarter:      Mapped[int | None]  = mapped_column(SmallInteger)
    month:        Mapped[int | None]  = mapped_column(SmallInteger)
    value:        Mapped[float | None]= mapped_column(Numeric(18, 4))
    source:       Mapped[str | None]
    fetched_at:   Mapped[str]         = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("country_id", "indicator_id", "year", "quarter", "month"),
    )

    country   = relationship("Country",   back_populates="indicator_values")
    indicator = relationship("Indicator", back_populates="values")
