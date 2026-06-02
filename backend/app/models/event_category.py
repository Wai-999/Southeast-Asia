from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class EventCategory(Base):
    __tablename__ = "event_categories"

    id:        Mapped[int]      = mapped_column(primary_key=True)
    code:      Mapped[str]      = mapped_column(String, unique=True, nullable=False)
    name:      Mapped[str]      = mapped_column(String, nullable=False)
    color_hex: Mapped[str|None] = mapped_column(String(7))
    icon_name: Mapped[str|None]

    news_events = relationship("NewsEvent", back_populates="category")
