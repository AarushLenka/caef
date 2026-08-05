"""SQLAlchemy models: Device, Event, Patch, HistoryRecord (TDD.md §2.8).

The History Table is append-only (TRD.md §5) and FKEY-linked back to device,
event and patch so any deployed artifact is traceable end-to-end (NFR-5).
Engine is driven by config.DATABASE_URL — Supabase Postgres in deployment,
SQLite for offline tests, no code difference.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

import config
from server.schemas import RecordStatus, RecordType, TriggerType


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. pi_node_alpha
    mcu_type: Mapped[str] = mapped_column(String)
    # A/B partition model (SAFETY_PROTOCOL.md §6): the previous active slot is
    # kept as inactive so "last known-good" is always immediately flashable.
    active_fw_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    inactive_fw_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_fw_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    last_poll_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Per-device strike counter (SAFETY_PROTOCOL.md §5). generation_halted stays
    # True until an operator acknowledges — never auto-resumes.
    strike_count: Mapped[int] = mapped_column(Integer, default=0)
    generation_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="device")
    history: Mapped[list["HistoryRecord"]] = relationship(back_populates="device")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType))
    event: Mapped[str] = mapped_column(String)  # e.g. HIGH_HEAT_DETECTED
    # Device is the clock (ARCHITECTURE.md §4.2); received_at is server-side only
    # for latency metrics.
    timestamp: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_state_hash: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    # Shared Guard Rail + Sandbox retry budget, per event (SAFETY_PROTOCOL.md §4).
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)

    device: Mapped[Device] = relationship(back_populates="events")
    patches: Mapped[list["Patch"]] = relationship(back_populates="event")


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    # Stored verbatim for audit (NFR-5): the plan, the code, and the tool-call
    # trace Guard Rail used to prove pin provenance.
    plan: Mapped[str] = mapped_column(Text)
    target_file: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(Text)
    pins_referenced: Mapped[list] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    fw_hash: Mapped[str] = mapped_column(String, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    guardrail_status: Mapped[str | None] = mapped_column(String, nullable=True)
    guardrail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox_status: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox_runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped[Event] = relationship(back_populates="patches")


class HistoryRecord(Base):
    """Append-only ledger: Time | Poll id | Event id | Patch id | FW hash."""

    __tablename__ = "history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    time: Mapped[int] = mapped_column(Integer)  # device-authoritative event time
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    poll_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    # Nullable for reversion/rollback rows that reference a prior patch's artifact
    # rather than introducing new code (DATA_SCHEMAS.md §7).
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("patches.id"), nullable=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    fw_hash: Mapped[str] = mapped_column(String)
    record_type: Mapped[RecordType] = mapped_column(Enum(RecordType))
    status: Mapped[RecordStatus] = mapped_column(Enum(RecordStatus))

    device: Mapped[Device] = relationship(back_populates="history")


engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
