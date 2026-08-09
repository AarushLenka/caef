"""Single source of tunables for the whole CAEF pipeline (TDD.md §6).

Any safety-relevant number (retry cap, sandbox timeout, reversion window,
forbidden pins, denylist) MUST be read from here, never inlined at the call
site. CLAUDE.md §4 treats an inline safety constant as a build failure.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


# --- Storage -----------------------------------------------------------------
# Structured store: Supabase Postgres in deployment, SQLite for offline tests.
# SQLAlchemy either way, so this is a connection-string swap (TDD.md §2.8).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'caef.db'}")

# RAG store: local SQLite FTS5 index, separate file from the structured store
# (TRD.md §5 permits one engine for both; we keep RAG local so E2E runs offline).
RAG_DB_PATH = Path(os.getenv("RAG_DB_PATH", ROOT / "caef_rag.db"))
# How many retrieved documents of each type reach the prompt (TDD.md §2.4).
RAG_DRIVER_DOC_LIMIT = _int("RAG_DRIVER_DOC_LIMIT", 5)
RAG_HISTORY_DOC_LIMIT = _int("RAG_HISTORY_DOC_LIMIT", 3)

HARDWARE_SCHEMA_DIR = Path(os.getenv("HARDWARE_SCHEMA_DIR", ROOT / "schemas"))
FIRMWARE_STORE_DIR = Path(os.getenv("FIRMWARE_STORE_DIR", ROOT / "firmware_store"))

# --- Safety ------------------------------------------------------------------
# Shared retry budget for Guard Rail + Sandbox failures, per event_id
# (SAFETY_PROTOCOL.md §4).
MAX_RETRIES = _int("MAX_RETRIES", 3)

# SAFETY_PROTOCOL.md §3.2
SANDBOX_TIMEOUT_SECONDS = _int("SANDBOX_TIMEOUT_SECONDS", 10)
SANDBOX_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "128m")
SANDBOX_CPU_LIMIT = os.getenv("SANDBOX_CPU_LIMIT", "0.5")
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "caef-sandbox:latest")
# The repo path as the *Docker daemon* sees it. Identical to ROOT when the
# runner is on the host; under docker-compose the runner is itself in a
# container talking to the host daemon, where `-v /app:...` would bind a path
# that does not exist on the host.
SANDBOX_HOST_REPO = Path(os.getenv("SANDBOX_HOST_REPO", ROOT))
# SAFETY_PROTOCOL.md §3.4: a candidate must emit this marker to count as healthy.
# The baseline firmware logs it on every tick; empty disables the check.
SANDBOX_HEALTHY_MARKER = os.getenv("SANDBOX_HEALTHY_MARKER", "[firmware]")
# Sandbox logs are stored on the Patch row for audit; cap so a chatty or looping
# candidate cannot bloat the DB.
SANDBOX_LOG_LIMIT_CHARS = _int("SANDBOX_LOG_LIMIT_CHARS", 20_000)

# SAFETY_PROTOCOL.md §5 — strikes are counted per device_id.
STRIKE_LIMIT = _int("STRIKE_LIMIT", 3)
# A device crash within this window of a deploy counts as a strike against it.
CRASH_ATTRIBUTION_WINDOW_SECONDS = _int("CRASH_ATTRIBUTION_WINDOW_SECONDS", 600)

# Situational Morphing reversion (LOOPS.md §2a, PRD OQ-1).
# v0.1 default is time-based; condition-based is the documented alternative.
REVERSION_WINDOW_SECONDS = _int("REVERSION_WINDOW_SECONDS", 300)
REVERSION_MODE = os.getenv("REVERSION_MODE", "time")  # time | condition | combined
REVERSION_RECOVERY_THRESHOLD_C = float(os.getenv("REVERSION_RECOVERY_THRESHOLD_C", 60.0))
# How often condition/combined mode re-checks the device's latest reading.
REVERSION_POLL_SECONDS = _int("REVERSION_POLL_SECONDS", 5)

# Guard Rail extras: forbidden_pins in the device schema is authoritative
# (DATA_SCHEMAS.md §1); this only adds pipeline-wide extensions on top.
EXTRA_FORBIDDEN_PINS = [int(p) for p in _list("EXTRA_FORBIDDEN_PINS", "")]

# SAFETY_PROTOCOL.md §2.4 starting set.
DENYLIST_IMPORTS = _list("DENYLIST_IMPORTS", "subprocess,ctypes,socketserver,multiprocessing")
DENYLIST_CALLS = _list("DENYLIST_CALLS", "eval,exec,compile,__import__,os.system,os.popen")

# --- Networking --------------------------------------------------------------
LISTENER_HOST = os.getenv("LISTENER_HOST", "127.0.0.1")
LISTENER_UDP_PORT = _int("LISTENER_UDP_PORT", 9500)  # heartbeats, best-effort
LISTENER_TCP_PORT = _int("LISTENER_TCP_PORT", 9501)  # events needing an ack
# Where the *device's* watchdog listens for OTA pushes. Same host as the
# Listener on a single-machine v0.1 run; separate when server and edge node are
# different containers/hosts (docker-compose), where LISTENER_HOST is the
# server's own bind address and cannot double as the device's address.
DEVICE_OTA_HOST = os.getenv("DEVICE_OTA_HOST", LISTENER_HOST)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = _int("API_PORT", 8000)  # frontend + /poll reconciliation endpoint
DASHBOARD_REFRESH_SECONDS = _int("DASHBOARD_REFRESH_SECONDS", 5)  # TDD.md §2.9 live feed

# --- Edge node ---------------------------------------------------------------
DEVICE_ID = os.getenv("DEVICE_ID", "pi_node_alpha")
SENSOR_TICK_SECONDS = _int("SENSOR_TICK_SECONDS", 1)  # LOOPS.md §1
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)  # LOOPS.md §3
OTA_PORT = _int("OTA_PORT", 9600)  # device watchdog listens here
HEAT_THRESHOLD_C = float(os.getenv("HEAT_THRESHOLD_C", 80.0))
# Source spec's post-trigger pause: device stops per-loop work while awaiting an
# OTA reply rather than re-firing the same trigger every tick (LOOPS.md §1).
POST_TRIGGER_HOLD_SECONDS = _int("POST_TRIGGER_HOLD_SECONDS", 20)
TELEMETRY_TIMEOUT_SECONDS = _int("TELEMETRY_TIMEOUT_SECONDS", 5)
# The firmware artifact the Agent regenerates (AgentOutput.target_file).
FIRMWARE_PATH = Path(os.getenv("FIRMWARE_PATH", ROOT / "edge_node" / "main.py"))
# Real DHT11s read a few degrees off; this is the per-device calibration knob,
# not a simulation cheat — it stays meaningful on physical hardware.
SENSOR_TEMP_OFFSET_C = float(os.getenv("SENSOR_TEMP_OFFSET_C", 0.0))
# Which physical situation the simulated sensors model: normal | heat.
# Crash behaviour is not a scenario flag — a faulty firmware is OTA-pushed, the
# same way a real regression would arrive.
SCENARIO = os.getenv("SCENARIO", "normal")

# --- Agent -------------------------------------------------------------------
# LangChain over an OpenAI-compatible endpoint; LLM_BASE_URL lets this point at
# OpenAI, OpenRouter, Groq or a local Ollama without a code change.
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.0))
# Cap on tool-call round trips within a single generation attempt, so a model
# that keeps calling check_hardware_schema without ever emitting code still
# terminates and burns exactly one retry (SAFETY_PROTOCOL.md §4).
AGENT_MAX_TOOL_TURNS = _int("AGENT_MAX_TOOL_TURNS", 8)
