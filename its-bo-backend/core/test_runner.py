"""
TestRunner – Orchestrace transportů a SSE live feed.

TestRunner je tenká vrstva nad SessionCoordinator:
- Generuje SSE events každou sekundu z get_live_stats()
- Řídí flow: start → live feed → stop → evaluate → save

SSE (Server-Sent Events) umožňuje frontend zobrazovat
live metriky v reálném čase bez pollingu.
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from core.session_coordinator import SessionCoordinator

logger = logging.getLogger("itsbo.core.test_runner")


class TestRunner:
    """
    Orchestrátor testů s SSE live feed.

    Generuje SSE events každou sekundu s aktuálními metrikami
    pro real-time zobrazení na frontendu.
    """

    def __init__(self, coordinator: SessionCoordinator) -> None:
        self._coordinator = coordinator

    async def live_stats_stream(
        self, session_id: str, interval_s: float = 1.0
    ) -> AsyncGenerator[str, None]:
        """
        Generátor SSE events s live statistikami.

        Každý event je JSON objekt s aktuálními metrikami.
        Stream končí když session opustí stav RUNNING.

        Args:
            session_id: identifikátor session.
            interval_s: interval mezi events (default 1s).

        Yields:
            str: SSE formátovaný event ("data: {...}\\n\\n").
        """
        logger.info("SSE stream started for session %s", session_id)

        while True:
            state = self._coordinator.get_session_state(session_id)
            if state is None:
                yield self._sse_event({"error": "session_not_found"})
                break

            stats = self._coordinator.get_live_stats(session_id)
            yield self._sse_event(stats)

            if state not in ("INIT", "BASELINE", "RUNNING"):
                # Session je v terminálním stavu
                logger.info(
                    "SSE stream ending for session %s (state=%s)", session_id, state
                )
                break

            await asyncio.sleep(interval_s)

    def _sse_event(self, data: dict) -> str:
        """Formátuje dict jako SSE event string."""
        return f"data: {json.dumps(data, default=str)}\n\n"
