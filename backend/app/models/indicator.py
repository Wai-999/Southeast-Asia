from sqlalchemy import String, Boolean, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Indicator(Base):
    __tablename__ = "indicators"

    id:               Mapped[int]  = mapped_column(primary_key=True)
    code:             Mapped[str]  = mapped_column(String, unique=True, nullable=False)
    name:             Mapped[str]  = mapped_column(String, nullable=False)
    description:      Mapped[str | None]
    unit:             Mapped[str]  = mapped_column(String, nullable=False)
    cadence:          Mapped[str]  = mapped_column(String, nullable=False)
    world_bank_code:  Mapped[str | None]
    imf_code:         Mapped[str | None]
    source_name:      Mapped[str]  = mapped_column(String, nullable=False)
    source_url:       Mapped[str | None]
    is_active:        Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            "cadence IN ('annual', 'quarterly', 'monthly', 'daily')",
            name="ck_cadence",
        ),
    )

    values      = relationship("IndicatorValue", back_populates="indicator")
    alert_rules = relationship("AlertRule",      back_populates="indicator")
