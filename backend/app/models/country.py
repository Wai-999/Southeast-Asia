from sqlalchemy import String, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Country(Base):
    __tablename__ = "countries"

    id:          Mapped[str] = mapped_column(String(3), primary_key=True)
    name:        Mapped[str] = mapped_column(String, nullable=False)
    region:      Mapped[str] = mapped_column(String, nullable=False)
    iso2:        Mapped[str] = mapped_column(String(2), nullable=False)
    currency:    Mapped[str] = mapped_column(String(3), nullable=False)
    capital:     Mapped[str | None]
    flag_emoji:  Mapped[str | None]

    __table_args__ = (
        CheckConstraint("region IN ('ASEAN', 'External Partner')", name="ck_region"),
    )

    indicator_values = relationship("IndicatorValue", back_populates="country")
    news_events      = relationship("NewsEvent",      back_populates="country")
    pattern_alerts   = relationship("PatternAlert",   back_populates="country")
