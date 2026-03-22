"""
UC-A: Extended Sensors / SDSM (Collective Perception Service).

Standard: 3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-004]
Higher degree of automation, range 500 m.

Normativní požadavky:
- Max E2E latence: ≤ 10 ms (aproximováno jako RTT/2)
- Spolehlivost (app-level): ≥ 99.99 %
- UL throughput: ≥ 25 Mbps (peak)
- UL payload: 1600 B @ 10 Hz (R.5.4-001)

Komunikační vzor (BIDIRECTIONAL):
- UL: OBU → ITS-BO: CPM-like zprávy 1600 B @ 10 Hz (burst_port, UDP)
- DL: ITS-BO → OBU: agregovaná situační mapa (control_port, UDP, 10 Hz)

DL chování:
AppLayerSimulator udržuje buffer přijatých objektů z posledních 500 ms.
Každých 100 ms odešle aktualizovanou mapu – simulace ITS-BO agregační
funkce dle TS 103 324 §6.1.
"""

import asyncio
import logging
from typing import Any

from config import UDP_RECV_BUFFER_BYTES
from core.base_uc import BaseUseCase, UCProfile
from transports.app_layer_simulator import AppLayerSimulator
from transports.burst_receiver import BurstReceiver

logger = logging.getLogger("itsbo.plugins.uc_a_sdsm")


class UcASdsm(BaseUseCase):
    """UC-A: Extended Sensors / SDSM – Collective Perception Service."""

    def __init__(self) -> None:
        self._ul_receiver: BurstReceiver | None = None
        self._dl_sender: AppLayerSimulator | None = None
        self._dl_task: asyncio.Task | None = None

    def profile(self) -> UCProfile:
        return UCProfile(
            id="UC-A",
            name="Extended Sensors / SDSM",
            standard_ref="3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-004]",
            description=(
                "Collective Perception – sdílení senzorových dat mezi "
                "vozidly/infrastrukturou. CPM zprávy 1600 B @ 10 Hz."
            ),
            communication_pattern="BIDIRECTIONAL",
            ul_transport="app_cpm",
            dl_transport="app_cpm_aggregated",
            thresholds={
                "e2e_latency_ms": {"value": 10, "op": "<=", "ref": "R.5.4-004"},
                "application_reliability_pct": {"value": 99.99, "op": ">=", "ref": "R.5.4-004"},
                "ul_throughput_mbps": {"value": 25, "op": ">=", "ref": "R.5.4-004"},
            },
            default_params={
                "payload_size_bytes": 1600,
                "tx_rate_hz": 10,
                "num_objects_per_cpm": 5,
                "aggregation_window_ms": 500,
            },
            baseline_required=True,
            min_repetitions=3,
            default_duration_s=60,
        )

    async def start(
        self,
        params: dict[str, Any],
        session_id: str,
        ports: dict[str, int],
        obu_ip: str,
    ) -> None:
        """
        1. Spustí BurstReceiver na ports["burst_port"] pro příjem CPM z OBU
        2. Spustí AppLayerSimulator pro DL – agregační mapa zpět na OBU
        3. Obě větve jako asyncio tasks
        """
        effective = {**self.profile().default_params, **params}

        # UL: BurstReceiver pro CPM příjem
        self._ul_receiver = BurstReceiver()
        await self._ul_receiver.start(
            port=ports["burst_port"],
            protocol="udp",
            session_id=session_id,
            recv_buffer_bytes=UDP_RECV_BUFFER_BYTES,
        )

        # DL: AppLayerSimulator – agregovaná mapa
        self._dl_sender = AppLayerSimulator()
        self._dl_task = asyncio.create_task(
            self._dl_sender.run_cpm_aggregation(
                target_ip=obu_ip,
                target_port=ports["control_port"],
                session_id=session_id,
                ul_receiver=self._ul_receiver,
                aggregation_window_ms=effective.get("aggregation_window_ms", 500),
                tx_rate_hz=effective.get("tx_rate_hz", 10),
            )
        )

        logger.info(
            "UC-A started: UL receiver on port %d, DL aggregation → %s:%d",
            ports["burst_port"], obu_ip, ports["control_port"],
        )

    async def stop(self, session_id: str) -> dict:
        """Zastaví obě větve, vrátí statistiky."""
        # Stop DL
        if self._dl_task and not self._dl_task.done():
            self._dl_task.cancel()
            try:
                await self._dl_task
            except asyncio.CancelledError:
                pass

        # Stop UL a získej stats
        stats = {}
        if self._ul_receiver:
            stats = self._ul_receiver.get_stats(session_id)
            await self._ul_receiver.stop(session_id)

        logger.info("UC-A stopped (session=%s)", session_id)
        return stats

    def get_live_stats(self, session_id: str) -> dict:
        """Live metriky pro SSE."""
        result = {"uc": "UC-A"}
        if self._ul_receiver:
            result["ul"] = self._ul_receiver.get_live_stats()
        return result

    def get_obu_instructions(self, params: dict[str, Any]) -> str:
        return (
            "OBU: Posílej CPM-like pakety (1600 B) na burst_port @ 10 Hz. "
            "Přijímej agregovanou situační mapu na control_port."
        )
