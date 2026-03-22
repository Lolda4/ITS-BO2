"""
PortAllocator – Dynamická alokace UDP portů per session.

Přiděluje volné porty z definovaných rozsahů (burst: 5100-5199,
control: 4500-4599). Při ukončení session se porty vrátí do poolu.

Řeší problém: souběžné sessions by jinak kolidovaly na pevných portech.
Asyncio Lock zajišťuje bezpečnost při paralelních session/init requestech.
"""

import asyncio
import logging

from config import (
    BURST_PORT_RANGE_END,
    BURST_PORT_RANGE_START,
    CONTROL_PORT_RANGE_END,
    CONTROL_PORT_RANGE_START,
)

logger = logging.getLogger("itsbo.core.port_allocator")


class PortAllocator:
    """
    Přiděluje volné porty z definovaných rozsahů per session.
    Při ukončení session se porty vrátí do poolu.
    Thread-safe přes asyncio.Lock.
    """

    def __init__(self) -> None:
        self._burst_pool: set[int] = set(
            range(BURST_PORT_RANGE_START, BURST_PORT_RANGE_END + 1)
        )
        self._control_pool: set[int] = set(
            range(CONTROL_PORT_RANGE_START, CONTROL_PORT_RANGE_END + 1)
        )
        self._allocated: dict[str, dict[str, int]] = {}  # session_id → {burst_port, control_port}
        self._lock = asyncio.Lock()

    async def allocate(self, session_id: str) -> dict[str, int]:
        """
        Přidělí burst_port a control_port pro danou session.

        Args:
            session_id: identifikátor session.

        Returns:
            dict: {"burst_port": int, "control_port": int}

        Raises:
            RuntimeError: pokud nejsou volné porty v poolu.
        """
        async with self._lock:
            if not self._burst_pool:
                raise RuntimeError(
                    "No free burst ports available "
                    f"(range {BURST_PORT_RANGE_START}-{BURST_PORT_RANGE_END})"
                )
            if not self._control_pool:
                raise RuntimeError(
                    "No free control ports available "
                    f"(range {CONTROL_PORT_RANGE_START}-{CONTROL_PORT_RANGE_END})"
                )

            bp = self._burst_pool.pop()
            cp = self._control_pool.pop()
            self._allocated[session_id] = {"burst_port": bp, "control_port": cp}

            logger.info(
                "Allocated ports for session %s: burst=%d, control=%d "
                "(remaining: burst=%d, control=%d)",
                session_id, bp, cp, len(self._burst_pool), len(self._control_pool),
            )

            return {"burst_port": bp, "control_port": cp}

    async def release(self, session_id: str) -> None:
        """
        Vrátí porty do poolu pro danou session.

        Args:
            session_id: identifikátor session jejíž porty uvolnit.
        """
        async with self._lock:
            if session_id in self._allocated:
                ports = self._allocated.pop(session_id)
                self._burst_pool.add(ports["burst_port"])
                self._control_pool.add(ports["control_port"])
                logger.info(
                    "Released ports for session %s: burst=%d, control=%d",
                    session_id, ports["burst_port"], ports["control_port"],
                )
            else:
                logger.warning("release() called for unknown session %s", session_id)

    def get_allocated(self, session_id: str) -> dict[str, int] | None:
        """Vrátí alokované porty pro session nebo None."""
        return self._allocated.get(session_id)

    @property
    def free_burst_count(self) -> int:
        """Počet volných burst portů."""
        return len(self._burst_pool)

    @property
    def free_control_count(self) -> int:
        """Počet volných control portů."""
        return len(self._control_pool)

    @property
    def active_sessions(self) -> int:
        """Počet sessions s alokovanými porty."""
        return len(self._allocated)
