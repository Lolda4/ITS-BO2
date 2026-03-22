"""
UC-B: See-Through (Video Sharing).

Standard: 3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-009]
Higher degree of automation, range 400 m.

Normativní požadavky:
- Max E2E latence: ≤ 10 ms
- Spolehlivost (app-level): ≥ 99.99 %
- Throughput (UL i DL): ≥ 10 Mbps

Komunikační vzor (BIDIRECTIONAL):
- UL: OBU → ITS-BO: video-like burst (H.264 GOP: I-frame ~50 KB, P-frame ~5 KB)
- DL: ITS-BO → OBU: symetrický video DL burst (infrastrukturní kamera)

DL video burst běží nezávisle na UL příjmu. Generátor produkuje GOP pattern:
1× I-frame (~50 KB, ~34 paketů), poté 29× P-frame (~5 KB, 3-4 pakety).
Cyklus 30 framů @ 30 fps = 1 sekunda.
"""

import asyncio
import logging
from typing import Any

from config import UDP_RECV_BUFFER_BYTES
from core.base_uc import BaseUseCase, UCProfile
from transports.app_layer_simulator import AppLayerSimulator
from transports.burst_receiver import BurstReceiver

logger = logging.getLogger("itsbo.plugins.uc_b_see_through")


class UcBSeeThrough(BaseUseCase):
    """UC-B: See-Through – Video Sharing."""

    def __init__(self) -> None:
        self._ul_receiver: BurstReceiver | None = None
        self._dl_sender: AppLayerSimulator | None = None
        self._dl_task: asyncio.Task | None = None
        self._dl_stats: dict = {}

    def profile(self) -> UCProfile:
        return UCProfile(
            id="UC-B",
            name="See-Through / Video Sharing",
            standard_ref="3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-009]",
            description=(
                "Video Sharing – sdílení videa z palubní kamery "
                "a příjem videa z infrastrukturní kamery. "
                "Symetrický video burst UL + DL."
            ),
            communication_pattern="BIDIRECTIONAL",
            ul_transport="app_video",
            dl_transport="app_video",
            thresholds={
                "e2e_latency_ms": {"value": 10, "op": "<=", "ref": "R.5.4-009"},
                "application_reliability_pct": {"value": 99.99, "op": ">=", "ref": "R.5.4-009"},
                "ul_throughput_mbps": {"value": 10, "op": ">=", "ref": "R.5.4-009"},
            },
            default_params={
                "ul_bitrate_mbps": 10.0,
                "dl_bitrate_mbps": 10.0,
                "fps": 30,
                "gop_size": 30,
                "iframe_size_bytes": 50000,
                "pframe_size_bytes": 5000,
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
        1. Spustí BurstReceiver na burst_port pro příjem UL video z OBU
        2. Spustí DL video sender (GOP pattern) na control_port → OBU
        3. Obě větve nezávisle v asyncio tasks
        """
        effective = {**self.profile().default_params, **params}

        # UL: BurstReceiver pro video příjem
        self._ul_receiver = BurstReceiver()
        await self._ul_receiver.start(
            port=ports["burst_port"],
            protocol="udp",
            session_id=session_id,
            recv_buffer_bytes=UDP_RECV_BUFFER_BYTES,
        )

        # DL: Video sender (GOP pattern)
        self._dl_sender = AppLayerSimulator()
        duration_s = effective.get("duration_s", 60)
        self._dl_task = asyncio.create_task(
            self._run_dl_video(
                obu_ip=obu_ip,
                target_port=ports["control_port"],
                session_id=session_id,
                bitrate_mbps=effective.get("dl_bitrate_mbps", 10.0),
                fps=effective.get("fps", 30),
                duration_s=duration_s,
            )
        )

        logger.info(
            "UC-B started: UL receiver on port %d, DL video → %s:%d @ %.1f Mbps",
            ports["burst_port"], obu_ip, ports["control_port"],
            effective.get("dl_bitrate_mbps", 10.0),
        )

    async def _run_dl_video(
        self,
        obu_ip: str,
        target_port: int,
        session_id: str,
        bitrate_mbps: float,
        fps: int,
        duration_s: float,
    ) -> None:
        """Wrapper pro DL video – ukládá stats po dokončení."""
        self._dl_stats = await self._dl_sender.run_video_dl(
            target_ip=obu_ip,
            target_port=target_port,
            session_id=session_id,
            bitrate_mbps=bitrate_mbps,
            fps=fps,
            duration_s=duration_s,
        )

    async def stop(self, session_id: str) -> dict:
        """Zastaví obě větve, vrátí UL + DL statistiky."""
        # Stop DL
        if self._dl_task and not self._dl_task.done():
            self._dl_task.cancel()
            try:
                await self._dl_task
            except asyncio.CancelledError:
                pass

        # Stop UL
        ul_stats = {}
        if self._ul_receiver:
            ul_stats = self._ul_receiver.get_stats(session_id)
            await self._ul_receiver.stop(session_id)

        return {
            **ul_stats,
            "dl": self._dl_stats,
        }

    def get_live_stats(self, session_id: str) -> dict:
        result = {"uc": "UC-B"}
        if self._ul_receiver:
            result["ul"] = self._ul_receiver.get_live_stats()
        return result

    def get_obu_instructions(self, params: dict[str, Any]) -> str:
        return (
            "OBU: Posílej video-like burst (H.264 GOP: I-frame 50 KB / P-frame 5 KB) "
            "na burst_port @ 10 Mbps. Přijímej DL video na control_port."
        )
