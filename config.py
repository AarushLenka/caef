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

# SAFETY_PROTOCOL.md §5 — strikes are counted per device_id.
STRIKE_LIMIT = _int("STRIKE_LIMIT", 3)
# A device crash within this window of a deploy counts as a strike against it.
CRASH_ATTRIBUTION_WINDOW_SECONDS = _int("CRASH_ATTRIBUTION_WINDOW_SECONDS", 600)

# Situational Morphing reversion (LOOPS.md §2a, PRD OQ-1).
# v0.1 default is time-based; condition-based is the documented alternative.
REVERSION_WINDOW_SECONDS = _int("REVERSION_WINDOW_SECONDS", 300)
REVERSION_MODE = os.getenv("REVERSION_MODE", "time")  # time | condition | combined
REVERSION_RECOVERY_THRESHOLD_C = float(os.getenv("REVERSION_RECOVERY_THRESHOLD_C", 60.0))

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
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = _int("API_PORT", 8000)  # frontend + /poll reconciliation endpoint

DEVICE_ID = os.getenv("DEVICE_ID", "pi_node_alpha")
SENSOR_TICK_SECONDS = _int("SENSOR_TICK_SECONDS", 1)  # LOOPS.md §1
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)  # LOOPS.md §3
OTA_PORT = _int("OTA_PORT", 9600)  # device watchdog listens here
HEAT_THRESHOLD_C = float(os.getenv("HEAT_THRESHOLD_C", 80.0))

# --- Agent -------------------------------------------------------------------
# LangChain over an OpenAI-compatible endpoint; LLM_BASE_URL lets this point at
# OpenAI, OpenRouter, Groq or a local Ollama without a code change.
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.0))
