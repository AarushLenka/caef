"""Server entrypoint: Listener + Distributor + Task consumer, one event loop.

v0.1 runs these in a single process (TRD.md §7 — local simulation is the correct
v0.1 form). The Distributor interface is what keeps them separable: swapping
LocalDistributor for SQS/SNS splits this into three processes without touching
Listener or Agent code.
"""

import asyncio
import logging

import config
from server.agent.agent import Agent, build_llm
from server.db.models import init_db
from server.distributor.distributor import LocalDistributor
from server.listener.listener import Listener
from server.orchestrator import Orchestrator
from server.schemas import EventNotification

log = logging.getLogger("caef")


def log_event(event: EventNotification) -> None:
    """Placeholder Event-topic subscriber standing in for the Frontend live feed
    (M9). Subscribing here proves the fan-out leg exists end-to-end."""
    log.info("EVENT %s %s device=%s", event.trigger_type, event.event, event.device_id)


async def serve() -> None:
    init_db()
    distributor = LocalDistributor()
    distributor.subscribe(log_event)
    orchestrator = Orchestrator(Agent(build_llm()))
    # Condition/combined reversion polls the device's latest reading, which only
    # reaches the scheduler through the Event topic (LOOPS.md §2a).
    distributor.subscribe(lambda event: _observe(orchestrator, event))
    listener = Listener(distributor)

    await listener.serve_tcp()
    await listener.serve_udp()
    log.info("CAEF server up (mode=%s, reversion=%s)", config.SCENARIO, config.REVERSION_MODE)
    await distributor.drain(orchestrator.handle)


def _observe(orchestrator: Orchestrator, event: EventNotification) -> None:
    """Feed the triggering metric to the reversion scheduler.

    `temp_c` is the v0.1 situation metric (PRD §6 Scenario A / OQ-1's recovery
    threshold); events that carry no reading are simply not observations.
    """
    reading = event.data.get("temp_c")
    if isinstance(reading, (int, float)):
        orchestrator.scheduler.observe(event.device_id, float(reading))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
