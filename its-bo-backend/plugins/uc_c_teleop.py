"""
UC-C: Tele-Operated Driving.

Standard: 3GPP TS 22.186 v18.0.1 Table 5.5-1 [R.5.5-002]
Nejvíce náročný UC – vyžaduje sub-5ms RTT.

Normativní požadavky:
- Max E2E latence (řídicí smyčka): ≤ 5 ms
- Spolehlivost (app-level): ≥ 99.999 %
- UL throughput (video + telemetrie): ≥ 25 Mbps
- DL throughput (řídicí příkazy): ≥ 1 Mbps

Komunikační vzor (BIDIRECTIONAL_ASYMMETRIC):
- UL větev: OBU → ITS-BO: BurstEngine UDP @ 25 Mbps
- DL větev: ITS-BO → OBU: UdpControlLoop MCM @ 10 Hz + ACK
- DVĚ paralelní nezávislé asyncio tasks

RTT měřeno na ITS-BO: ack_receive_time_us − mcm_send_time_us
(obě timestamps z jednoho hostu = nepotřebuje NTP).
"""

import asyncio
import logging
from typing import Any

from config import UDP_RECV_BUFFER_BYTES
from core.base_uc import BaseUseCase, UCProfile
from transports.app_layer_simulator import AppLayerSimulator
from transports.burst_receiver import BurstReceiver
from transports.udp_control_loop import UdpControlLoop

logger = logging.getLogger("itsbo.plugins.uc_c_teleop")


class UcCTeleOp(BaseUseCase):
    """UC-C: Tele-Operated Driving – řídicí smyčka s RTT měřením."""

    def __init__(self) -> None:
        self._ul_receiver: BurstReceiver | None = None
        self._dl_control: UdpControlLoop | None = None
        self._mcm_factory_instance: AppLayerSimulator | None = None

    def profile(self) -> UCProfile:
        return UCProfile(
            id="UC-C",
            name="Tele-Operated Driving",
            standard_ref="3GPP TS 22.186 v18.0.1 Table 5.5-1 [R.5.5-002]",
            description=(
                "Dálkově ovládané řízení – kritická řídicí smyčka s nejpřísnějšími "
                "požadavky na latenci a spolehlivost. UL video 25 Mbps + DL MCM 10 Hz."
            ),
            communication_pattern="BIDIRECTIONAL_ASYMMETRIC",
            ul_transport="burst_udp",
            dl_transport="app_control",
            thresholds={
                "e2e_latency_ms": {"value": 5, "op": "<=", "ref": "R.5.5-002"},
                "application_reliability_pct": {"value": 99.999, "op": ">=", "ref": "R.5.5-002"},
                "ul_throughput_mbps": {"value": 25, "op": ">=", "ref": "R.5.5-002"},
                "dl_throughput_mbps": {"value": 1, "op": ">=", "ref": "R.5.5-002"},
            },
            default_params={
                "ul_bitrate_mbps": 25.0,
                "control_interval_ms": 100,
                "control_packet_size": 256,
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
        Spustí DVĚ paralelní větve jako nezávislé asyncio tasks:
        1. UL: BurstReceiver na ports["burst_port"] pro 25 Mbps video stream z OBU
        2. DL: UdpControlLoop na ports["control_port"] – MCM @ 10 Hz s RTT měřením
        """
        effective = {**self.profile().default_params, **params}

        # UL větev – video příjem
        self._ul_receiver = BurstReceiver()
        await self._ul_receiver.start(
            port=ports["burst_port"],
            protocol="udp",
            session_id=session_id,
            recv_buffer_bytes=UDP_RECV_BUFFER_BYTES,
        )

        # DL větev – řídicí smyčka
        self._mcm_factory_instance = AppLayerSimulator()
        self._dl_control = UdpControlLoop()
        await self._dl_control.run(
            target_ip=obu_ip,
            local_port=ports["control_port"],
            session_id=session_id,
            interval_ms=effective.get("control_interval_ms", 100),
            packet_size=effective.get("control_packet_size", 256),
            payload_factory=self._mcm_factory,
        )

        logger.info(
            "UC-C started: UL on port %d, DL control on port %d → %s",
            ports["burst_port"], ports["control_port"], obu_ip,
        )

    def _mcm_factory(self, seq: int, session_id: str) -> bytes:
        """Factory pro MCM payload – deleguje na AppLayerSimulator."""
        return self._mcm_factory_instance.build_mcm(seq, session_id)

    async def stop(self, session_id: str) -> dict:
        """Zastaví obě větve, vrátí UL + DL statistiky."""
        # Stop DL control loop
        dl_stats = {}
        if self._dl_control:
            dl_stats = self._dl_control.get_stats(session_id)
            await self._dl_control.stop()

        # Stop UL receiver
        ul_stats = {}
        if self._ul_receiver:
            ul_stats = self._ul_receiver.get_stats(session_id)
            await self._ul_receiver.stop(session_id)

        return {
            **ul_stats,
            "dl": dl_stats,
        }

    def get_live_stats(self, session_id: str) -> dict:
        """Live metriky: UL throughput + DL RTT."""
        result = {"uc": "UC-C"}
        if self._ul_receiver:
            result["ul"] = self._ul_receiver.get_live_stats()
        if self._dl_control:
            result["dl"] = self._dl_control.get_live_stats()
        return result

    def get_obu_instructions(self, params: dict[str, Any]) -> str:
        return (
            "OBU: Posílej UDP burst @ 25 Mbps na burst_port (video UL). "
            "Přijímej MCM na control_port+1000, okamžitě odesílej ACK "
            "[seq:4B][0xAC:1B][processing_ns:8B] zpět na control_port."
        )
