"""
BurstSender – asyncio UDP/TCP sender generující provoz dle UC profilu.

Přesný inter-packet timing pomocí asyncio.sleep kompenzovaného o skutečný
elapsed. Používá se pro DL sending v UC-B (video) a obecně pro generování
testovacího provozu směrem k OBU.

Inter-packet interval = (packet_size * 8) / (bitrate_mbps * 1e6) sekund.
Kompenzace: pokud odeslání trvalo déle než plánováno, příští sleep se zkrátí.
"""

import asyncio
import logging
import socket
import time
from typing import Callable, Optional

logger = logging.getLogger("itsbo.transport.burst_sender")


class BurstSender:
    """
    asyncio UDP/TCP sender generující provoz dle UC profilu.

    Cílový bitrate je řízen přes inter-packet interval s adaptivní kompenzací
    skutečného elapsed – pokud OS scheduling způsobí prodlevu, další interval
    se zkrátí aby průměrný bitrate zůstal na cíli.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._send_task: Optional[asyncio.Task] = None
        self._stats: dict = {}

    async def run(
        self,
        target_ip: str,
        target_port: int,
        bitrate_mbps: float,
        packet_size: int,
        payload_factory: Callable[[int], bytes],
        session_id: str,
        duration_s: float,
    ) -> dict:
        """
        Vysílá pakety cílovým bitratem po dobu duration_s.

        Args:
            target_ip: IP adresa cíle (OBU).
            target_port: UDP port cíle.
            bitrate_mbps: cílový bitrate v Mbps.
            packet_size: velikost jednoho paketu v bytes.
            payload_factory: callable(seq) → bytes, generuje payload per paket.
            session_id: identifikátor session pro logování.
            duration_s: doba vysílání v sekundách.

        Returns:
            dict: statistiky odesílání (throughput, jitter, counts).
        """
        self._running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()

        interval_s = (packet_size * 8) / (bitrate_mbps * 1_000_000)
        seq = 0
        start = time.monotonic()
        next_send = start
        sent_bytes = 0
        send_times: list[float] = []

        logger.info(
            "BurstSender started: %s:%d @ %.2f Mbps, interval=%.6fs, duration=%.1fs (session=%s)",
            target_ip, target_port, bitrate_mbps, interval_s, duration_s, session_id,
        )

        try:
            while self._running and (time.monotonic() - start) < duration_s:
                now = time.monotonic()
                if now < next_send:
                    await asyncio.sleep(next_send - now)

                payload = payload_factory(seq)
                actual_send_time = time.monotonic()
                try:
                    await loop.sock_sendto(sock, payload, (target_ip, target_port))
                    sent_bytes += len(payload)
                    send_times.append(actual_send_time)
                except Exception as e:
                    logger.warning("BurstSender send error: %s", e)

                next_send += interval_s
                seq += 1

        except asyncio.CancelledError:
            logger.info("BurstSender cancelled (session=%s)", session_id)
        finally:
            sock.close()

        end_time = time.monotonic()
        elapsed = end_time - start
        if elapsed == 0:
            elapsed = 0.001

        # Send jitter: průměrná odchylka od plánovaného inter-packet intervalu
        if len(send_times) > 1:
            intervals = [send_times[i + 1] - send_times[i] for i in range(len(send_times) - 1)]
            deviations = [abs(iv - interval_s) for iv in intervals]
            send_jitter_ms = sum(deviations) / len(deviations) * 1000
        else:
            send_jitter_ms = 0.0

        self._stats = {
            "throughput_mbps_actual": round((sent_bytes * 8) / elapsed / 1_000_000, 3),
            "throughput_mbps_target": bitrate_mbps,
            "send_jitter_ms": round(send_jitter_ms, 3),
            "packets_sent": seq,
            "bytes_sent": sent_bytes,
            "elapsed_s": round(elapsed, 2),
        }

        logger.info(
            "BurstSender finished: sent %d packets (%.2f Mbps actual, %.2f target) session=%s",
            seq, self._stats["throughput_mbps_actual"], bitrate_mbps, session_id,
        )

        return self._stats

    def get_stats(self) -> dict:
        """Vrátí aktuální statistiky (i pokud sender ještě běží)."""
        return self._stats.copy() if self._stats else {}

    async def stop(self) -> None:
        """Zastaví sender předčasně."""
        self._running = False
        if self._send_task and not self._send_task.done():
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
