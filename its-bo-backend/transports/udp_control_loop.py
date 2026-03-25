"""
UdpControlLoop – Bidirectionální UDP pro UC-C řídicí smyčku.

KRITICKÁ komponenta pro měření E2E latence řídicí smyčky:

ITS-BO posílá MCM zprávy → OBU okamžitě odesílá ACK → ITS-BO měří RTT.

RTT = ack_receive_time_us − mcm_send_time_us

Obě timestamps jsou z ITS-BO clock (time.monotonic), tedy z JEDNOHO hostu –
nepotřebuje NTP/PTP synchronizaci mezi ITS-BO a OBU.

E2E latence je aproximována jako RTT/2. Asymetrie UL/DL je omezení
této aproximace, uvedené v diplomce.

ACK payload od OBU:
    [seq: 4B big-endian]
    [ack_flag: 1B (0xAC)]
    [obu_processing_time_ns: 8B big-endian]

obu_processing_time_ns = čas od přijetí MCM do odeslání ACK na OBU straně
(lokální měření – nepotřebuje clock sync).
"""

import asyncio
import logging
import socket
import time
from typing import Callable, Optional
from core.audit_logger import audit_logger

logger = logging.getLogger("itsbo.transport.udp_control_loop")


class UdpControlLoop:
    """
    Bidirectionální UDP řídicí smyčka pro UC-C.

    Paralelní send loop (MCM @ 10 Hz) a recv loop (ACK) na JEDNOM socketu.
    Párování ACK s MCM přes seq číslo v dict _sent_mcm[seq] = send_timestamp_us.
    """

    def __init__(self) -> None:
        self._sent_mcm: dict[int, int] = {}  # seq → send_timestamp_us
        self._rtt_samples: list[dict] = []
        self._packets_sent: int = 0
        self._acks_received: int = 0
        self._running: bool = False
        self._start_time: float = 0.0
        self._send_task: Optional[asyncio.Task] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._sock: Optional[socket.socket] = None

    @property
    def last_packet_time(self) -> float:
        """Timestamp posledního přijatého ACK."""
        if self._rtt_samples:
            return self._rtt_samples[-1]["recv_time_us"] / 1_000_000
        return self._start_time

    async def run(
        self,
        target_ip: str,
        local_port: int,
        session_id: str,
        interval_ms: int = 100,
        packet_size: int = 256,
        payload_factory: Optional[Callable[[int, str], bytes]] = None,
    ) -> None:
        """
        Spustí řídicí smyčku:
        1. Send loop: posílá MCM @ interval_ms Hz
        2. Recv loop: přijímá ACK na stejném socketu
        3. Páruje ACK s MCM přes seq číslo, počítá RTT

        OBU naslouchá na local_port + 1000 (konvence z specifikace).

        Args:
            target_ip: IP adresa OBU.
            local_port: lokální port pro bind (= control_port).
            session_id: identifikátor session.
            interval_ms: interval mezi MCM (default 100 = 10 Hz).
            packet_size: velikost MCM payloadu (default 256 B).
            payload_factory: callable(seq, session_id) → bytes.
                             Pokud None, používá interní MCM factory.
        """
        self._running = True
        self._start_time = time.monotonic()
        self._sent_mcm = {}
        self._rtt_samples = []
        self._packets_sent = 0
        self._acks_received = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)  # 1 MB
        self._sock.setblocking(False)
        self._sock.bind(("0.0.0.0", local_port))

        loop = asyncio.get_event_loop()
        interval_s = interval_ms / 1000
        # OBU naslouchá na control_port + 1000
        target_port = local_port + 1000

        logger.info(
            "UdpControlLoop started on port %d → %s:%d @ %d ms (session=%s)",
            local_port, target_ip, target_port, interval_ms, session_id,
        )

        # Paralelní send a receive
        self._send_task = asyncio.create_task(
            self._send_loop(
                self._sock, loop, target_ip, target_port, interval_s,
                payload_factory, session_id,
            )
        )
        self._recv_task = asyncio.create_task(self._recv_loop(self._sock, loop, session_id))

    async def _send_loop(
        self,
        sock: socket.socket,
        loop: asyncio.AbstractEventLoop,
        target_ip: str,
        target_port: int,
        interval_s: float,
        payload_factory: Optional[Callable],
        session_id: str,
    ) -> None:
        """
        Posílá MCM zprávy v pravidelných intervalech.
        Každý MCM má seq číslo a timestamp_us z ITS-BO clock.
        """
        from transports.app_layer_simulator import AppLayerSimulator

        simulator = AppLayerSimulator()
        seq = 0
        next_send = time.monotonic()

        try:
            while self._running:
                now = time.monotonic()
                if now < next_send:
                    await asyncio.sleep(next_send - now)

                send_time_us = int(time.monotonic() * 1_000_000)

                if payload_factory:
                    payload = payload_factory(seq, session_id)
                else:
                    payload = simulator.build_mcm(seq, session_id)

                self._sent_mcm[seq] = send_time_us

                try:
                    await loop.sock_sendto(sock, payload, (target_ip, target_port))
                    self._packets_sent += 1
                    audit_logger.log_event(session_id, "DL", "Tx_MCM", {
                        "seq": seq, "size_B": len(payload), "send_time_us": send_time_us
                    })
                except Exception as e:
                    logger.warning("MCM send error (seq=%d): %s", seq, e)

                next_send += interval_s
                seq += 1

        except asyncio.CancelledError:
            pass

    async def _recv_loop(
        self,
        sock: socket.socket,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
    ) -> None:
        """
        Přijímá ACK od OBU.

        ACK formát: [seq:4B big-endian][ack_flag:1B (0xAC)][obu_processing_ns:8B]

        Páruje s odeslaným MCM přes seq číslo a počítá RTT.
        """
        try:
            while self._running:
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), timeout=1.0
                    )
                    recv_time_us = int(time.monotonic() * 1_000_000)

                    # Parse ACK: [seq:4B][ack_flag:1B][obu_processing_ns:8B]
                    if len(data) >= 13 and data[4] == 0xAC:
                        ack_seq = int.from_bytes(data[0:4], "big")
                        obu_processing_ns = int.from_bytes(data[5:13], "big")

                        if ack_seq in self._sent_mcm:
                            rtt_us = recv_time_us - self._sent_mcm[ack_seq]
                            self._rtt_samples.append(
                                {
                                    "seq": ack_seq,
                                    "rtt_us": rtt_us,
                                    "obu_processing_us": obu_processing_ns / 1000,
                                    "recv_time_us": recv_time_us,
                                }
                            )
                            self._acks_received += 1
                            audit_logger.log_event(session_id, "UL", "Rx_ACK", {
                                "seq": ack_seq, "rtt_us": rtt_us, "obu_proc_us": obu_processing_ns / 1000
                            })
                        else:
                            logger.debug(
                                "ACK for unknown seq %d (may have timed out)", ack_seq
                            )
                    else:
                        logger.debug(
                            "Received non-ACK packet (%d B) from %s", len(data), addr
                        )

                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Zastaví obě smyčky a zavře socket."""
        self._running = False
        for task in [self._send_task, self._recv_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        logger.info(
            "UdpControlLoop stopped: sent=%d, acked=%d",
            self._packets_sent, self._acks_received,
        )

    def _elapsed_s(self) -> float:
        """Elapsed time od startu smyčky."""
        return time.monotonic() - self._start_time

    def get_stats(self, session_id: str) -> dict:
        """
        Kompletní statistiky řídicí smyčky.

        RTT statistiky: avg, min, max, p50, p95, p99.
        Jitter: průměrná variace po sobě jdoucích RTT hodnot.
        Packet loss: 1 - (acks_received / packets_sent).

        Returns:
            dict: kompletní RTT a loss statistiky.
        """
        if not self._rtt_samples:
            return {
                "avg_rtt_ms": None,
                "min_rtt_ms": None,
                "max_rtt_ms": None,
                "p50_rtt_ms": None,
                "p95_rtt_ms": None,
                "p99_rtt_ms": None,
                "jitter_ms": None,
                "packet_loss_pct": 100.0 if self._packets_sent > 0 else 0.0,
                "packets_sent": self._packets_sent,
                "acks_received": 0,
                "control_loop_hz_actual": 0.0,
                "rtt_sample_count": 0,
            }

        rtts_ms = sorted(s["rtt_us"] / 1000 for s in self._rtt_samples)
        n = len(rtts_ms)

        return {
            "avg_rtt_ms": round(sum(rtts_ms) / n, 3),
            "min_rtt_ms": round(rtts_ms[0], 3),
            "max_rtt_ms": round(rtts_ms[-1], 3),
            "p50_rtt_ms": round(rtts_ms[int(n * 0.5)], 3),
            "p95_rtt_ms": round(rtts_ms[min(int(n * 0.95), n - 1)], 3),
            "p99_rtt_ms": round(rtts_ms[min(int(n * 0.99), n - 1)], 3),
            "jitter_ms": round(self._calc_jitter(rtts_ms), 3),
            "packet_loss_pct": round(
                (1 - self._acks_received / max(self._packets_sent, 1)) * 100, 4
            ),
            "packets_sent": self._packets_sent,
            "acks_received": self._acks_received,
            "control_loop_hz_actual": round(
                self._packets_sent / max(self._elapsed_s(), 0.001), 2
            ),
            "rtt_sample_count": n,
        }

    def get_live_stats(self) -> dict:
        """Odlehčená verze pro SSE live feed."""
        if not self._rtt_samples:
            return {
                "avg_rtt_ms": None,
                "packets_sent": self._packets_sent,
                "acks_received": self._acks_received,
            }

        recent = self._rtt_samples[-100:]  # posledních 100 vzorků
        rtts_ms = [s["rtt_us"] / 1000 for s in recent]
        return {
            "avg_rtt_ms": round(sum(rtts_ms) / len(rtts_ms), 3),
            "p95_rtt_ms": round(sorted(rtts_ms)[min(int(len(rtts_ms) * 0.95), len(rtts_ms) - 1)], 3),
            "packets_sent": self._packets_sent,
            "acks_received": self._acks_received,
            "packet_loss_pct": round(
                (1 - self._acks_received / max(self._packets_sent, 1)) * 100, 4
            ),
        }

    def _calc_jitter(self, sorted_rtts: list[float]) -> float:
        """
        Jitter = průměrná variace po sobě jdoucích RTT hodnot.
        Předpokládá seřazený list RTT v ms.
        """
        if len(sorted_rtts) < 2:
            return 0.0
        diffs = [
            abs(sorted_rtts[i + 1] - sorted_rtts[i])
            for i in range(len(sorted_rtts) - 1)
        ]
        return sum(diffs) / len(diffs)
