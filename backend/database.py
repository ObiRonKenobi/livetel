from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from models import Base

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    inspector = inspect(engine)
    needs_reset = False

    if not inspector.has_table("cdrs"):
        needs_reset = True
    else:
        cols = {c["name"] for c in inspector.get_columns("cdrs")}
        if "call_id" not in cols or "from_uri" not in cols:
            needs_reset = True

    if needs_reset:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS cdrs"))
            conn.execute(text("DROP TABLE IF EXISTS alerts"))

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if inspector.has_table("cdrs"):
        cdr_indexes = {idx["name"] for idx in inspector.get_indexes("cdrs")}
        if "ix_cdrs_timestamp" not in cdr_indexes:
            with engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cdrs_timestamp ON cdrs (timestamp)"))

    inspector = inspect(engine)
    if inspector.has_table("alerts"):
        alert_cols = {c["name"] for c in inspector.get_columns("alerts")}
        if "severity" not in alert_cols:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alerts"))
            Base.metadata.create_all(bind=engine)
        elif "dismissed_status" not in alert_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE alerts ADD COLUMN dismissed_status VARCHAR"))
        elif "dismissed_at" not in alert_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE alerts ADD COLUMN dismissed_at DATETIME"))
