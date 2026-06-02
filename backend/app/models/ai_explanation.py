from sqlalchemy import ForeignKey, SmallInteger, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class AiExplanation(Base):
    __tablename__ = "ai_explanations"

    id:               Mapped[int]      = mapped_column(primary_key=True)
    country_id:       Mapped[str]      = mapped_column(ForeignKey("countries.id"), nullable=False)
    indicator_id:     Mapped[int|None] = mapped_column(ForeignKey("indicators.id"))
    alert_id:         Mapped[int|None] = mapped_column(ForeignKey("pattern_alerts.id"))
    explanation_type: Mapped[str]      = mapped_column(String, nullable=False)
    year:             Mapped[int|None] = mapped_column(SmallInteger)
    quarter:          Mapped[int|None] = mapped_column(SmallInteger)
    prompt_used:      Mapped[str|None] = mapped_column(Text)
    explanation_text: Mapped[str]      = mapped_column(Text, nullable=False)
    model_used:       Mapped[str]      = mapped_column(String, default="claude-haiku-4-5")
    generated_at:     Mapped[str]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    country   = relationship("Country")
    indicator = relationship("Indicator")
    alert     = relationship("PatternAlert", back_populates="explanation")
