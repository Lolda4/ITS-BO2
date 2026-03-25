"""
BurstReceiver – asyncio UDP/TCP server přijímající strukturované pakety od OBU.

Nahrazuje iPerf3 server s přidanou hodnotou: V2X-aware per-packet tracking
včetně seq čísel, timestampů a session identifikace v payloadu.

Payload formát příchozích paketů (RFC 5357 základ):
    [seq_number: 4B big-endian]
    [timestamp_ns: 8B big-endian]
    [uc_id: 2B big-endian]
    [session_hash: 4B big-endian]
    [data: NB]

Klíčové vlastnosti:
- SO_RCVBUF nastavený na 4 MB (konfigurabilní) – prevence kernel buffer
  overflow při 25 Mbps UL
- Per-packet tracking: každý paket zalogován s seq, arrival timestamp, velikostí
- Detekce chybějících seq čísel pro přesný packet loss
- Monitorování /proc/net/udp pro detekci kernel drops
- Jitter výpočet dle RFC 3550 (variace inter-arrival)
"""

import asyncio
import logging
import os
import socket
import time
from typing import Optional

from config import UDP_RECV_BUFFER_BYTES
from core.audit_logger import audit_logger

logger = logging.getLogger("itsbo.transport.burst_receiver")


class BurstReceiver:
    """
    asyncio UDP server pro příjem strukturovaných burst paketů.

    Používá se pro UL příjem ve všech UC – BurstEngine na OBU straně
    odesílá pakety s binary header obsahujícím seq číslo a timestamp,
    BurstReceiver je přijímá a počítá metriky.
    """

    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._packets: list[tuple[int, int, int, int]] = []  # (seq, arrival_us, size, sender_ts_ns)
        self._bytes_received: int = 0
        self._start_time: float = 0.0
        self._last_packet_time: float = 0.0
        self._running: bool = False
        self._recv_task: Optional[asyncio.Task] = None

    @property
    def last_packet_time(self) -> float:
        """Monotonic timestamp posledního přijatého paketu."""
        return self._last_packet_time

    async def start(
        self,
        port: int,
        protocol: str,
        session_id: str,
        recv_buffer_bytes: int = UDP_RECV_BUFFER_BYTES,
    ) -> None:
        """
        Vytvoří UDP socket s rozšířeným receive bufferem a spustí recv loop.

        Po vytvoření socketu OVĚŘÍ skutečnou velikost bufferu – kernel může
        ořezat požadovanou hodnotu pokud net.core.rmem_max je nižší.
        V takovém případě loguje WARNING s instrukcí pro sysctl.

        Args:
            port: UDP port na kterém naslouchat.
            protocol: "udp" (TCP zatím neimplementováno pro receiver).
            session_id: identifikátor session pro logování.
            recv_buffer_bytes: požadovaná velikost SO_RCVBUF (default 4 MB).
        """
        if protocol != "udp":
            raise ValueError(f"BurstReceiver podporuje pouze UDP, dostal: {protocol}")

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer_bytes)

        # Ověření skutečné velikosti bufferu (kernel může ořezat)
        actual_buf = self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        if actual_buf < recv_buffer_bytes:
            logger.warning(
                "UDP buffer requested %d but got %d. "
                "Zvyš net.core.rmem_max: sudo sysctl -w net.core.rmem_max=%d",
                recv_buffer_bytes,
                actual_buf,
                recv_buffer_bytes * 2,
            )

        self._sock.setblocking(False)
        self._sock.bind(("0.0.0.0", port))

        self._packets = []
        self._bytes_received = 0
        self._start_time = time.monotonic()
        self._last_packet_time = time.monotonic()
        self._running = True

        logger.info(
            "BurstReceiver started on port %d (session=%s, buffer=%d/%d)",
            port, session_id, actual_buf, recv_buffer_bytes,
        )

        self._recv_task = asyncio.create_task(self._recv_loop(session_id))

    async def _recv_loop(self, session_id: str) -> None:
        """
        Hlavní příjímací smyčka. Parsuje binary header a ukládá per-packet data.
        Timeout 1s zajišťuje periodické check zda _running je stále True.
        """
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(self._sock, 65536), timeout=1.0
                )
                arrival_us = int(time.monotonic() * 1_000_000)
                self._last_packet_time = time.monotonic()

                # Parse binary header: [seq:4B][ts_ns:8B][uc_id:2B][session_hash:4B]
                if len(data) >= 18:
                    seq = int.from_bytes(data[0:4], "big")
                    ts_ns = int.from_bytes(data[4:12], "big")
                    # uc_id a session_hash parsujeme ale neukládáme – slouží pro routing
                    self._packets.append((seq, arrival_us, len(data), ts_ns))
                    self._bytes_received += len(data)
                    audit_logger.log_event(session_id, "UL", "Rx_Data", {
                        "seq": seq, "size_B": len(data), "arrival_us": arrival_us, "sender_ts_ns": ts_ns
                    })
                else:
                    # Malý paket – stále započítáme bytes ale nemáme seq
                    self._bytes_received += len(data)
                    logger.debug(
                        "BurstReceiver got undersized packet (%d B) from %s",
                        len(data), addr,
                    )

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.error("BurstReceiver recv error: %s", e)

    async def stop(self, session_id: str) -> None:
        """Zastaví recv loop a zavře socket."""
        self._running = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        logger.info("BurstReceiver stopped (session=%s)", session_id)

    def get_stats(self, session_id: str) -> dict:
        """
        Vypočítá statistiky z přijatých paketů.

        Packet loss: detekce chybějících seq čísel v rozsahu [min_seq, max_seq].
        Toto je přesnější než porovnání s "očekávaným" počtem, protože neznáme
        kolik paketů OBU skutečně odeslal (to přijde v obu_stats při session/stop).

        Jitter dle RFC 3550: průměr |inter-arrival_n - inter-arrival_{n-1}|.

        Returns:
            dict s klíči: throughput_mbps, packet_loss_pct, jitter_ms,
            packets_received, packets_expected, bytes_received, elapsed_s,
            kernel_buffer_drops, recv_buffer_bytes_actual.
        """
        elapsed_s = time.monotonic() - self._start_time
        if elapsed_s == 0:
            elapsed_s = 0.001

        if self._packets:
            seqs = sorted(p[0] for p in self._packets)
            expected_min, expected_max = seqs[0], seqs[-1]
            expected_count = expected_max - expected_min + 1
            received_unique = len(set(seqs))
            missing = expected_count - received_unique
            loss_pct = (missing / expected_count * 100) if expected_count > 0 else 0

            # Jitter (RFC 3550): průměr |inter-arrival_n - inter-arrival_{n-1}|
            arrivals = [p[1] for p in self._packets]
            inter_arrivals = [arrivals[i + 1] - arrivals[i] for i in range(len(arrivals) - 1)]
            if len(inter_arrivals) > 1:
                jitter_values = [
                    abs(inter_arrivals[i + 1] - inter_arrivals[i])
                    for i in range(len(inter_arrivals) - 1)
                ]
                jitter_ms = sum(jitter_values) / len(jitter_values) / 1000
            else:
                jitter_ms = 0.0
        else:
            loss_pct = 100.0
            jitter_ms = 0.0
            missing = 0
            expected_count = 0

        kernel_drops = self._read_kernel_drops()

        return {
            "throughput_mbps": round(
                (self._bytes_received * 8) / elapsed_s / 1_000_000, 3
            ),
            "packet_loss_pct": round(loss_pct, 4),
            "jitter_ms": round(jitter_ms, 3),
            "packets_received": len(self._packets),
            "packets_expected": expected_count,
            "bytes_received": self._bytes_received,
            "elapsed_s": round(elapsed_s, 2),
            "kernel_buffer_drops": kernel_drops,
            "recv_buffer_bytes_actual": (
                self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                if self._sock and self._sock.fileno() != -1
                else 0
            ),
        }

    def get_live_stats(self) -> dict:
        """Odlehčená verze get_stats pro SSE live feed (voláno každou sekundu)."""
        elapsed_s = time.monotonic() - self._start_time
        if elapsed_s == 0:
            elapsed_s = 0.001

        return {
            "throughput_mbps": round(
                (self._bytes_received * 8) / elapsed_s / 1_000_000, 3
            ),
            "packets_received": len(self._packets),
            "bytes_received": self._bytes_received,
            "elapsed_s": round(elapsed_s, 2),
        }

    def _read_kernel_drops(self) -> int:
        """
        Čte /proc/net/udp pro socket drops.

        Na Linuxu /proc/net/udp obsahuje řádek pro každý UDP socket,
        sloupec 13 (0-indexed 12) = drops. Identifikace přes inode.

        Na non-Linux systémech vrací -1 (nedostupné).
        """
        if not self._sock or self._sock.fileno() == -1:
            return -1
        try:
            inode = os.fstat(self._sock.fileno()).st_ino
            with open("/proc/net/udp") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 13 and parts[9] == str(inode):
                        return int(parts[12])
        except (OSError, FileNotFoundError, ValueError):
            pass
        return -1  # nedostupné (non-Linux)
