from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CDR(Base):
    __tablename__ = "cdrs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    src: Mapped[str] = mapped_column(String)
    dst: Mapped[str] = mapped_column(String)
    duration: Mapped[int] = mapped_column(Integer)
    mos: Mapped[float] = mapped_column(Float)
    latency: Mapped[float] = mapped_column(Float)
    jitter: Mapped[float] = mapped_column(Float)
    packet_loss: Mapped[float] = mapped_column(Float)
    sip_code: Mapped[int] = mapped_column(Integer)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    type: Mapped[str] = mapped_column(String)
    details: Mapped[str] = mapped_column(String)
