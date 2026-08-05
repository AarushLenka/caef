"""Server entrypoint: Listener + Distributor + Task consumer, one event loop.

v0.1 runs these in a single process (TRD.md §7 — local simulation is the correct
v0.1 form). The Distributor interface is what keeps them separable: swapping
LocalDistributor for SQS/SNS splits this into three processes without touching
Listener or Agent code.
"""

import asyncio
import logging

from server.agent.stub_agent import StubAgent
from server.db.models import init_db
from server.distributor.distributor import LocalDistributor
from server.listener.listener import Listener
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
    agent = StubAgent()
    listener = Listener(distributor)

    await listener.serve_tcp()
    await listener.serve_udp()
    log.info("CAEF server up (stub agent — no generation until M4/M5 land)")
    await distributor.drain(agent.handle)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
