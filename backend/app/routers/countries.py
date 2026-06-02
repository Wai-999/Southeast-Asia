from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Country

router = APIRouter()


@router.get("/")
def list_countries(region: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Country)
    if region:
        q = q.filter(Country.region == region)
    return q.order_by(Country.region, Country.name).all()


@router.get("/{country_id}")
def get_country(country_id: str, db: Session = Depends(get_db)):
    country = db.query(Country).filter(Country.id == country_id.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_id}' not found")
    return country
