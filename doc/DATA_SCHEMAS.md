# DATA_SCHEMAS.md
## CAEF Pipeline — Canonical Data Structures

All components must conform to these shapes. If an implementation needs a
field not listed here, extend this document first, then the code — schemas
are the contract, not an afterthought.

---

## 1. Device Hardware Schema (`schema_dev01.json`)

**Read-only to the Agent.** Represents physical reality; never modified by
generated code or by the Agent, only by an operator/provisioning step.

```json
{
  "device_id": "pi_node_alpha",
  "mcu_type": "RaspberryPi_4B",
  "constraints": {
    "max_gpio_current": "16mA",
    "forbidden_pins": [0, 1]
  },
  "pinout": {
    "GPIO_17": {
      "connected_device": "DHT11",
      "type": "sensor",
      "protocol": "digital_1wire",
      "status": "available"
    },
    "GPIO_27": {
      "connected_device": "Relay_Fan",
      "type": "actuator",
      "active_level": "HIGH",
      "status": "dormant"
    },
    "GPIO_22": {
      "connected_device": "Lidar_X2",
      "type": "sensor",
      "protocol": "UART",
      "status": "dormant"
    }
  }
}
```

**Field notes:**
- `status`: one of `available`, `dormant`, `active`, `forbidden`. `dormant` = physically connected but not in the currently-running code. `forbidden` pins must never appear in generated code (Guard Rail enforced).
- `forbidden_pins` in `constraints` is the authoritative denylist; `status: "forbidden"` on an individual pin entry is a secondary/explicit marker — both must be checked (defense in depth, per TRD §6).

## 2. Telemetry Payload

Sent from device to Listener.

```json
{
  "id": "pi_node_alpha",
  "timestamp": 171542000,
  "trigger_type": "CONTEXT_TRIGGER",
  "event": "HIGH_HEAT_DETECTED",
  "data": {
    "temp_c": 85.4,
    "threshold": 80.0
  },
  "current_state_hash": "a1b2c3d4"
}
```

- `trigger_type`: `CONTEXT_TRIGGER` | `CRITICAL_FAILURE`.
- `timestamp`: device-authoritative (Architecture §4.2 — "the device is the clock").
- `current_state_hash`: hash of the firmware currently running on the device at emission time — used to detect drift against the server's assigned-firmware record (feeds the Poll/Reconciliation Loop).
- For `CRITICAL_FAILURE`, `data` additionally carries `trace` (stack trace string) instead of/alongside sensor values, e.g. `{"trace": "IndexError: list index out of range ..."}`.

## 3. Agent Task (Distributor → Agent)

```json
{
  "task_id": "uuid",
  "event_id": "uuid",
  "device_id": "pi_node_alpha",
  "trigger_type": "CONTEXT_TRIGGER",
  "event": "HIGH_HEAT_DETECTED",
  "raw_payload": { "...": "the original telemetry payload" },
  "retry_count": 0
}
```

## 4. Agent Output (Agent → Guard Rail → Sandbox)

```json
{
  "patch_id": "uuid",
  "event_id": "uuid",
  "device_id": "pi_node_alpha",
  "plan": "Enable Relay_Fan on GPIO_27 (dormant → active). Remove Lidar_X2 driver to free CPU. Loop holds fan HIGH until temp < 60C.",
  "target_file": "main.py",
  "code": "<full file contents as string>",
  "pins_referenced": [27],
  "tool_calls": [
    { "tool": "check_hardware_schema", "args": { "pin_number": 27 }, "result": "SAFE: Connected to Relay_Fan" }
  ]
}
```

- `pins_referenced` and `tool_calls` exist specifically so Guard Rail can verify FR-12/NFR-3 mechanically (every referenced pin has a corresponding successful tool call) without re-parsing the code's prose plan.

## 5. Guard Rail Result

```json
{
  "patch_id": "uuid",
  "status": "pass",
  "checks": {
    "forbidden_pin_check": "pass",
    "tool_call_provenance": "pass",
    "schema_conformance": "pass",
    "static_safety_denylist": "pass",
    "current_draw_sanity": "pass"
  },
  "reason": null
}
```

On rejection, `status: "fail"` and `reason` is a human-readable explanation (also stored for audit and fed back to the Agent identically to a Sandbox failure — see LOOPS.md §2/§4).

## 6. Sandbox Result

```json
{
  "patch_id": "uuid",
  "status": "pass",
  "runtime_seconds": 10,
  "exit_code": 0,
  "logs": "...",
  "results": null,
  "delta_firmware": null
}
```

On failure:

```json
{
  "patch_id": "uuid",
  "status": "fail",
  "runtime_seconds": 2,
  "exit_code": 1,
  "logs": "Traceback ...",
  "results": "Process exited with code 1 after 2s",
  "delta_firmware": "<diff between attempted code and last-known-good code>"
}
```

This is the literal `FAIL (Results, ΔFirmware)` artifact from the architecture diagram.

## 6a. OTA Push Payload (Deploy → Device Watchdog)

Sent server → device over the watchdog's TCP port. `fw_hash` is verified by the
device before it writes the file (TRD §6: integrity, not code-signing, for v0.1).

```json
{
  "device_id": "pi_node_alpha",
  "fw_hash": "a1b2c3d4",
  "target_file": "main.py",
  "code": "<full file contents as string>",
  "patch_id": "uuid",
  "record_type": "morph_deploy"
}
```

Device replies on the same connection:

```json
{ "device_id": "pi_node_alpha", "status": "accepted", "fw_hash": "a1b2c3d4", "reason": null }
```

- `status`: `accepted` | `rejected`. `rejected` carries a `reason` (e.g.
  `hash_mismatch`) and the device keeps running its current firmware — a failed
  push must never leave the device in an unsafe or half-written state (NFR-6).
- `record_type` mirrors the History Table enum (§7) so the device's own log line
  distinguishes a morph from a patch from a rollback.

## 6b. Poll / Reconciliation (Device → Server)

The `Poll id / firmware` and `Polled Poll(id)` exchange from ARCHITECTURE §3.
Device sends `GET /poll?id=<device_id>&current_state_hash=<hash>`; server replies:

```json
{
  "poll_id": "uuid",
  "device_id": "pi_node_alpha",
  "assigned_fw_hash": "a1b2c3d4",
  "in_sync": true
}
```

- `poll_id` is generated per poll and is the value stored in `history.poll_id`.
- `in_sync` is `false` when `assigned_fw_hash` differs from the device's reported
  `current_state_hash`; the device then re-requests the artifact directly
  (`GET /firmware?id=<device_id>`, returning an OTA Push Payload as above). This
  is the missed-push safety net (LOOPS.md §3).

## 7. History Table (canonical ledger row)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | |
| `time` | timestamp | device-authoritative event time, plus a separate `received_at`/`deployed_at` for server-side timing |
| `poll_id` | string/nullable | last poll id associated with this record, if applicable |
| `event_id` | UUID (FKEY → `events.id`) | |
| `patch_id` | UUID (FKEY → `patches.id`, nullable for pure reversion/rollback rows referencing a prior patch) | |
| `device_id` | string (FKEY → `devices.id`) | |
| `fw_hash` | string | hash of the deployed firmware artifact |
| `record_type` | enum | `morph_deploy` \| `patch_deploy` \| `reversion` \| `rollback` |
| `status` | enum | `deployed` \| `superseded` \| `failed` |

## 8. RAG Document Types

| Type | Source | Purpose |
|---|---|---|
| **Docs of Node** | Per-device hardware schema + current connection/context schema | Grounds the Agent in physical reality for a specific device |
| **Docs on comp.** | Sensor Driver Library (validated snippets, e.g. `DHT11` class, `MPU6050` I2C setup) | Reusable, pre-vetted code the Agent should prefer over writing drivers from scratch |
| **History** | Prior `Event`/`Patch`/`HistoryRecord` rows | Grounds the Agent in "what worked last time for a similar failure/context" |

## 9. Naming Consistency Rule

Field and event names in code must match this document exactly
(`trigger_type`, `CONTEXT_TRIGGER`, `CRITICAL_FAILURE`, `current_state_hash`,
`fw_hash`, `patch_id`, `event_id`, `poll_id`, `device_id`). If a future change
renames one of these, update this file in the same commit.
