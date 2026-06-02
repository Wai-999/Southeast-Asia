from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import NewsEvent

router = APIRouter()


@router.get("/")
def get_news(
    country_id: str | None = Query(None),
    category: str | None = Query(None, description="Category code, e.g. 'economy'"),
    sentiment: str | None = Query(None),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(NewsEvent)
    if country_id:
        q = q.filter(NewsEvent.country_id == country_id.upper())
    if sentiment:
        q = q.filter(NewsEvent.sentiment == sentiment)
    if category:
        from ..models import EventCategory
        q = q.join(EventCategory).filter(EventCategory.code == category)
    return (
        q.order_by(NewsEvent.published_at.desc())
        .limit(limit)
        .all()
    )
