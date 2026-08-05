"""Pydantic mirrors of DATA_SCHEMAS.md — the wire contract between components.

Field names here are copied verbatim from that document (DATA_SCHEMAS.md §9,
naming consistency rule). Renaming a field here without updating the doc in the
same commit is a build failure per CLAUDE.md §4.
"""

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

import config


class TriggerType(StrEnum):
    CONTEXT_TRIGGER = "CONTEXT_TRIGGER"
    CRITICAL_FAILURE = "CRITICAL_FAILURE"


class PinStatus(StrEnum):
    AVAILABLE = "available"
    DORMANT = "dormant"
    ACTIVE = "active"
    FORBIDDEN = "forbidden"


class RecordType(StrEnum):
    MORPH_DEPLOY = "morph_deploy"
    PATCH_DEPLOY = "patch_deploy"
    REVERSION = "reversion"
    ROLLBACK = "rollback"


class RecordStatus(StrEnum):
    DEPLOYED = "deployed"
    SUPERSEDED = "superseded"
    FAILED = "failed"


# --- §1 Device Hardware Schema ----------------------------------------------


class PinEntry(BaseModel):
    connected_device: str
    type: str
    status: PinStatus
    protocol: str | None = None
    active_level: str | None = None


class SchemaConstraints(BaseModel):
    max_gpio_current: str
    forbidden_pins: list[int] = Field(default_factory=list)


class HardwareSchema(BaseModel):
    """Read-only to the Agent — enforced at the tool layer, not by convention."""

    device_id: str
    mcu_type: str
    constraints: SchemaConstraints
    pinout: dict[str, PinEntry]

    def pin(self, pin_number: int) -> PinEntry | None:
        return self.pinout.get(f"GPIO_{pin_number}")

    def is_forbidden(self, pin_number: int) -> bool:
        """All three denylists are authoritative (DATA_SCHEMAS.md §1 field notes
        plus config.EXTRA_FORBIDDEN_PINS as a pipeline-wide extension)."""
        entry = self.pin(pin_number)
        return (
            pin_number in self.constraints.forbidden_pins
            or pin_number in config.EXTRA_FORBIDDEN_PINS
            or (entry is not None and entry.status is PinStatus.FORBIDDEN)
        )


def load_hardware_schema(device_id: str) -> HardwareSchema:
    """Read the device's hardware schema. Read-only by construction: nothing in
    the pipeline ever writes back through this path (SAFETY_PROTOCOL.md §1)."""
    path = config.HARDWARE_SCHEMA_DIR / f"schema_{device_id}.json"
    if not path.exists():  # v0.1 ships one example device schema
        path = config.HARDWARE_SCHEMA_DIR / "schema_dev01.json"
    return HardwareSchema.model_validate(json.loads(path.read_text()))


# --- §2 Telemetry Payload ----------------------------------------------------


class TelemetryPayload(BaseModel):
    id: str
    timestamp: int  # device-authoritative (ARCHITECTURE.md §4.2)
    trigger_type: TriggerType
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    current_state_hash: str


# --- §3 Agent Task -----------------------------------------------------------


class AgentTask(BaseModel):
    task_id: str
    event_id: str
    device_id: str
    trigger_type: TriggerType
    event: str
    raw_payload: dict[str, Any]
    retry_count: int = 0


# --- §4 Agent Output ---------------------------------------------------------


class ToolCallRecord(BaseModel):
    tool: str
    args: dict[str, Any]
    result: str


class AgentOutput(BaseModel):
    patch_id: str
    event_id: str
    device_id: str
    plan: str
    target_file: str
    code: str
    pins_referenced: list[int] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


# --- §5 Guard Rail Result ----------------------------------------------------


class GuardRailChecks(BaseModel):
    forbidden_pin_check: Literal["pass", "fail"]
    tool_call_provenance: Literal["pass", "fail"]
    schema_conformance: Literal["pass", "fail"]
    static_safety_denylist: Literal["pass", "fail"]
    current_draw_sanity: Literal["pass", "fail"]


class GuardRailResult(BaseModel):
    patch_id: str
    status: Literal["pass", "fail"]
    checks: GuardRailChecks
    reason: str | None = None


# --- §6 Sandbox Result -------------------------------------------------------


class SandboxResult(BaseModel):
    patch_id: str
    status: Literal["pass", "fail"]
    runtime_seconds: float
    exit_code: int
    logs: str = ""
    results: str | None = None
    delta_firmware: str | None = None


# --- §6a OTA Push ------------------------------------------------------------


class OTAPush(BaseModel):
    device_id: str
    fw_hash: str
    target_file: str
    code: str
    patch_id: str | None = None
    record_type: RecordType


class OTAAck(BaseModel):
    device_id: str
    status: Literal["accepted", "rejected"]
    fw_hash: str
    reason: str | None = None


# --- §6b Poll / Reconciliation ----------------------------------------------


class PollResponse(BaseModel):
    poll_id: str
    device_id: str
    assigned_fw_hash: str | None
    in_sync: bool


def fw_hash(code: str) -> str:
    """Canonical firmware hash. One implementation, used by device, deploy and
    History Table alike, so `current_state_hash` and `fw_hash` are comparable."""
    return hashlib.sha256(code.encode()).hexdigest()[:16]
