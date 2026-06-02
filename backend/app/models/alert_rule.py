from sqlalchemy import ForeignKey, Numeric, String, Boolean, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id:           Mapped[int]  = mapped_column(primary_key=True)
    indicator_id: Mapped[int]  = mapped_column(ForeignKey("indicators.id"), nullable=False)
    name:         Mapped[str]  = mapped_column(String, nullable=False)
    description:  Mapped[str|None]
    condition:    Mapped[str]  = mapped_column(String, nullable=False)
    threshold:    Mapped[float]= mapped_column(Numeric, nullable=False)
    period:       Mapped[str]  = mapped_column(String, nullable=False)
    severity:     Mapped[str]  = mapped_column(String, nullable=False)
    is_active:    Mapped[bool] = mapped_column(Boolean, default=True)
    created_at:   Mapped[str]  = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("condition IN ('above','below','change_pct','change_abs')", name="ck_condition"),
        CheckConstraint("severity  IN ('info','warning','critical')",               name="ck_severity"),
    )

    indicator      = relationship("Indicator",    back_populates="alert_rules")
    pattern_alerts = relationship("PatternAlert", back_populates="alert_rule")
