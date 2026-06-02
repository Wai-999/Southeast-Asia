from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import countries, indicators, trade, news, alerts, explanations

app = FastAPI(
    title="SEA Change Dashboard API",
    description="Backend API for the Southeast Asia Economic & Political Change Dashboard",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(countries.router,    prefix="/countries",  tags=["Countries"])
app.include_router(indicators.router,   prefix="/indicators", tags=["Indicators"])
app.include_router(trade.router,        prefix="/trade",      tags=["Trade"])
app.include_router(news.router,         prefix="/news",       tags=["News"])
app.include_router(alerts.router,       prefix="/alerts",     tags=["Alerts"])
app.include_router(explanations.router, prefix="/explain",    tags=["AI Explanations"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}
