from sqlalchemy import ForeignKey, Numeric, String, Boolean, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class PatternAlert(Base):
    __tablename__ = "pattern_alerts"

    id:            Mapped[int]      = mapped_column(primary_key=True)
    country_id:    Mapped[str]      = mapped_column(ForeignKey("countries.id"), nullable=False)
    alert_rule_id: Mapped[int]      = mapped_column(ForeignKey("alert_rules.id"), nullable=False)
    indicator_id:  Mapped[int]      = mapped_column(ForeignKey("indicators.id"), nullable=False)
    trigger_value: Mapped[float]    = mapped_column(Numeric, nullable=False)
    threshold:     Mapped[float]    = mapped_column(Numeric, nullable=False)
    severity:      Mapped[str]      = mapped_column(String, nullable=False)
    message:       Mapped[str]      = mapped_column(Text, nullable=False)
    triggered_at:  Mapped[str]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at:   Mapped[str|None] = mapped_column(DateTime(timezone=True))
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','critical')", name="ck_pa_severity"),
    )

    country    = relationship("Country",   back_populates="pattern_alerts")
    alert_rule = relationship("AlertRule", back_populates="pattern_alerts")
    indicator  = relationship("Indicator")
    explanation= relationship("AiExplanation", back_populates="alert", uselist=False)
