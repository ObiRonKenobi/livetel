from contextlib import asynccontextmanager
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import engine, ensure_schema, get_db
from models import Base
from routers import alerts, cdrs, metrics
from schemas import AppConfigResponse, HealthResponse
from services.generator import baseline_traffic, inject_anomaly
from services.monitor import check_ollama_health, monitor_and_alert
from services.pruning import prune_old_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    scheduler.add_job(
        baseline_traffic,
        "interval",
        seconds=2,
        id="baseline_traffic",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=10,
    )
    scheduler.add_job(inject_anomaly, "interval", minutes=5, id="inject_anomaly")
    scheduler.add_job(monitor_and_alert, "interval", seconds=30, id="monitor_and_alert")
    scheduler.add_job(prune_old_data, "interval", minutes=15, id="prune_old_data")
    scheduler.start()
    logger.info("LiveTel backend started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("LiveTel backend stopped")


app = FastAPI(
    title="LiveTel API",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(metrics.router)
app.include_router(alerts.router)
app.include_router(cdrs.router)

health_router = APIRouter(prefix="/api", tags=["health"])


@health_router.get("/config", response_model=AppConfigResponse)
def get_app_config() -> AppConfigResponse:
    return AppConfigResponse(read_only=settings.read_only_demo)


@health_router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    ollama_ok = check_ollama_health()
    status = "ok" if db_ok else "degraded"
    return HealthResponse(status=status, db=db_ok, ollama=ollama_ok)


app.include_router(health_router)
