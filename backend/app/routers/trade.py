from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import TradeFlow

router = APIRouter()


@router.get("/{country_id}")
def get_trade_flows(
    country_id: str,
    year: int | None = Query(None),
    direction: str | None = Query(None, description="'export' or 'import'"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    q = db.query(TradeFlow).filter(TradeFlow.reporter_id == country_id.upper())
    if year:
        q = q.filter(TradeFlow.year == year)
    if direction:
        q = q.filter(TradeFlow.direction == direction)
    return (
        q.order_by(TradeFlow.year.desc(), TradeFlow.value_usd_m.desc())
        .limit(limit)
        .all()
    )
