from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import IndicatorValue

router = APIRouter()


@router.get("/{country_id}")
def get_indicator_values(
    country_id: str,
    year: int | None = Query(None, description="Filter by year"),
    indicator_code: str | None = Query(None, description="Filter by indicator code"),
    db: Session = Depends(get_db),
):
    q = (
        db.query(IndicatorValue)
        .filter(IndicatorValue.country_id == country_id.upper())
    )
    if year:
        q = q.filter(IndicatorValue.year == year)
    if indicator_code:
        from ..models import Indicator
        q = q.join(Indicator).filter(Indicator.code == indicator_code)
    return q.order_by(IndicatorValue.year.desc(), IndicatorValue.quarter).all()
