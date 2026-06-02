from sqlalchemy import ForeignKey, String, Numeric, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class NewsEvent(Base):
    __tablename__ = "news_events"

    id:              Mapped[int]        = mapped_column(primary_key=True)
    country_id:      Mapped[str]        = mapped_column(ForeignKey("countries.id"), nullable=False)
    category_id:     Mapped[int|None]   = mapped_column(ForeignKey("event_categories.id"))
    headline:        Mapped[str]        = mapped_column(Text, nullable=False)
    summary:         Mapped[str|None]   = mapped_column(Text)
    source_name:     Mapped[str|None]
    source_url:      Mapped[str|None]
    published_at:    Mapped[str]        = mapped_column(DateTime(timezone=True), nullable=False)
    sentiment:       Mapped[str|None]   = mapped_column(String)
    sentiment_score: Mapped[float|None] = mapped_column(Numeric(4, 3))
    fetched_at:      Mapped[str]        = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("sentiment IN ('positive', 'neutral', 'negative')", name="ck_sentiment"),
    )

    country  = relationship("Country",       back_populates="news_events")
    category = relationship("EventCategory", back_populates="news_events")
    impacts  = relationship("ImpactScore",   back_populates="news_event", cascade="all, delete-orphan")
