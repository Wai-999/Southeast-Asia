from sqlalchemy import ForeignKey, SmallInteger, String, CheckConstraint, UniqueConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class ImpactScore(Base):
    __tablename__ = "impact_scores"

    id:               Mapped[int] = mapped_column(primary_key=True)
    news_event_id:    Mapped[int] = mapped_column(ForeignKey("news_events.id", ondelete="CASCADE"))
    country_id:       Mapped[str] = mapped_column(ForeignKey("countries.id"))
    indicator_id:     Mapped[int] = mapped_column(ForeignKey("indicators.id"))
    impact_level:     Mapped[int] = mapped_column(SmallInteger, nullable=False)
    impact_direction: Mapped[str] = mapped_column(String, nullable=False)
    rationale:        Mapped[str|None] = mapped_column(Text)
    scored_at:        Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("impact_level BETWEEN 1 AND 5",                                name="ck_impact_level"),
        CheckConstraint("impact_direction IN ('positive','negative','neutral')",        name="ck_impact_dir"),
        UniqueConstraint("news_event_id", "country_id", "indicator_id"),
    )

    news_event = relationship("NewsEvent",  back_populates="impacts")
    country    = relationship("Country")
    indicator  = relationship("Indicator")
