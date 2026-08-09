# CAEF — Context-Aware Evolutionary Firmware

An edge device asks a cloud agent for a live firmware change — either to adapt
to what its sensors are seeing (*Situational Morphing*) or to heal itself after
a crash (*Auto-Patching*). Every generated change is schema-constrained,
Guard-Railed, sandboxed, and auto-reversible.

Design lives in [`doc/`](doc): [PRD](doc/PRD.md) · [TRD](doc/TRD.md) ·
[TDD](doc/TDD.md) · [ARCHITECTURE](doc/ARCHITECTURE.md) ·
[LOOPS](doc/LOOPS.md) · [DATA_SCHEMAS](doc/DATA_SCHEMAS.md) ·
[SAFETY_PROTOCOL](doc/SAFETY_PROTOCOL.md).

## Demo

```sh
echo 'LLM_API_KEY=sk-...' > .env
docker compose up --build
open http://localhost:8000
```

The dashboard streams the live event feed and the History Table. `SCENARIO=heat`
in `.env` drives the heat event; a crash is provoked by OTA-pushing a faulty
artifact, the same way a real regression would arrive.

## Tests

```sh
pip install -r requirements.txt
python -c 'from server.sandbox import sandbox_runner as s; s.build_image()'
pytest
```

`tests/test_e2e_scenarios.py` runs the three PRD §6 scenarios against the real
pipeline — real sockets, real Docker sandbox, a real watchdog subprocess. Only
the LLM is scripted. Without Docker the sandbox fails closed by design, so that
module skips rather than passing vacuously.

## Layout

| Path | What |
|---|---|
| `edge_node/` | Pi simulator: sensor loop, telemetry, OTA watchdog |
| `server/listener/` | Telemetry Gateway (UDP heartbeats, TCP events) |
| `server/distributor/` | Task queue + Event topic behind one interface |
| `server/agent/` | Agentic Core — the in-pipeline LLM, RAG, hardware-schema tool |
| `server/guardrail/` | Static gate: AST denylist, forbidden pins, schema conformance |
| `server/sandbox/` | Verification Sandbox — confined, time-boxed execution |
| `server/deploy/` | A/B rollout, reversion scheduler, Safety Rollback Protocol |
| `frontend/` | Operator dashboard: live feed, History Table, manual rollback |
| `config.py` | Every safety-relevant tunable (TDD §6) |
