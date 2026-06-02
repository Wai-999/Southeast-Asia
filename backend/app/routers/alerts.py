from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import PatternAlert

router = APIRouter()


@router.get("/")
def get_alerts(
    country_id: str | None = Query(None),
    severity: str | None = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    q = db.query(PatternAlert)
    if country_id:
        q = q.filter(PatternAlert.country_id == country_id.upper())
    if severity:
        q = q.filter(PatternAlert.severity == severity)
    if active_only:
        q = q.filter(PatternAlert.is_active == True)
    return q.order_by(PatternAlert.triggered_at.desc()).all()
