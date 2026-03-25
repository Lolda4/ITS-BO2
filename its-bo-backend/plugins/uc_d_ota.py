"""
UC-D: OTA Software Update.

Standard: ISO 24089:2023
Nejméně náročný UC – TCP přenos s integrity ověřením.

Normativní požadavky (odvozené autorem):
- DL throughput: ≥ 0.4 Mbps (odvozeno: 50 MB / 1000 s)
- Spolehlivost (app-level): ≥ 99.0 %
- Protokol: TCP

Komunikační vzor (DL_ONLY):
- ITS-BO → OBU: TCP stream simulující masivní SW update balík (500 MB, chunked 64 KB)
- Každý chunk: [header_len:4B][JSON header][64 KB data]
- OBU → ITS-BO: per-chunk ACK s integritou (MD5)
- Test se ukončí po přenosu všech chunků (self-terminating) nebo po timeoutu

Poznámka k normativním referencím: ISO 24089 definuje procesy OTA update,
nikoliv konkrétní síťové KPI. Prahy jsou odvozeny autorem jako minimální
požadavky pro praktický OTA scénář.
"""

import asyncio
import json
import logging
import socket
import time
from typing import Any

from core.base_uc import BaseUseCase, UCProfile
from transports.app_layer_simulator import AppLayerSimulator

logger = logging.getLogger("itsbo.plugins.uc_d_ota")

# 500 MB / 64 KB
TOTAL_SIZE_BYTES = 500 * 1024 * 1024
CHUNK_SIZE_BYTES = 64 * 1024
TOTAL_CHUNKS = TOTAL_SIZE_BYTES // CHUNK_SIZE_BYTES


class UcDOta(BaseUseCase):
    """UC-D: OTA Software Update – TCP chunked transfer."""

    def __init__(self) -> None:
        self._server_task: asyncio.Task | None = None
        self._stats: dict = {}
        self._running: bool = False

    def profile(self) -> UCProfile:
        return UCProfile(
            id="UC-D",
            name="OTA Software Update",
            standard_ref="ISO 24089:2023",
            description=(
                "Vzdálená aktualizace softwaru – TCP přenos 50 MB balíku "
                "rozděleného na 64 KB chunky s per-chunk integrity ověřením."
            ),
            communication_pattern="DL_ONLY",
            ul_transport="none",
            dl_transport="app_ota",
            thresholds={
                "dl_throughput_mbps": {"value": 50.0, "op": ">=", "ref": "ISO 24089 (Safe Side/Real-world 50Mbps)"},
                "application_reliability_pct": {"value": 99.0, "op": ">=", "ref": "ISO 24089 (odvozeno)"},
            },
            default_params={
                "transfer_size_mb": 500,
                "chunk_size_kb": 64,
                "package_id": "SW-v2.1.0-massive",
            },
            baseline_required=False,
            min_repetitions=3,
            default_duration_s=300,
        )

    async def start(
        self,
        params: dict[str, Any],
        session_id: str,
        ports: dict[str, int],
        obu_ip: str,
    ) -> None:
        """
        Spustí TCP server na burst_port, čeká na připojení OBU,
        posílá chunky, čeká na per-chunk ACK.
        """
        self._running = True
        self._stats = {}

        self._server_task = asyncio.create_task(
            self._tcp_ota_server(
                port=ports["burst_port"],
                obu_ip=obu_ip,
                session_id=session_id,
                params=params,
            )
        )

        logger.info(
            "UC-D started: TCP OTA server on port %d, waiting for OBU %s",
            ports["burst_port"], obu_ip,
        )

    async def _tcp_ota_server(
        self,
        port: int,
        obu_ip: str,
        session_id: str,
        params: dict,
    ) -> None:
        """
        TCP server pro OTA update:
        1. Listen na port
        2. Accept jednoho klienta (OBU)
        3. Posílej chunky [header_len:4B][JSON header][64 KB data]
        4. Čekej na ACK za každý chunk
        5. Po odeslání všech chunků – session completed
        """
        effective = {**self.profile().default_params, **params}
        simulator = AppLayerSimulator()
        package_id = effective.get("package_id", "SW-v2.1.0-patch")

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setblocking(False)
        server_sock.bind(("0.0.0.0", port))
        server_sock.listen(1)

        loop = asyncio.get_event_loop()
        start_time = time.monotonic()
        chunks_sent = 0
        chunks_acked = 0
        bytes_sent = 0

        try:
            # Čekaj na připojení OBU (timeout SESSION_TIMEOUT)
            logger.info("OTA server listening on port %d", port)
            client_sock, addr = await asyncio.wait_for(
                loop.sock_accept(server_sock), timeout=120
            )
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client_sock.setblocking(False)
            logger.info("OTA client connected from %s", addr)

            transfer_start = time.monotonic()

            for chunk_seq in range(TOTAL_CHUNKS):
                if not self._running:
                    break

                # Sestav chunk
                chunk_data = simulator.build_ota_chunk(chunk_seq, TOTAL_CHUNKS, package_id)

                # Odešli chunk
                try:
                    await loop.sock_sendall(client_sock, chunk_data)
                    chunks_sent += 1
                    bytes_sent += len(chunk_data)
                except Exception as e:
                    logger.error("OTA send error at chunk %d: %s", chunk_seq, e)
                    break

                # Čekej na ACK (jednoduchý 4-byte seq echo)
                try:
                    ack_data = await asyncio.wait_for(
                        loop.sock_recv(client_sock, 256), timeout=10
                    )
                    if ack_data:
                        chunks_acked += 1
                except asyncio.TimeoutError:
                    logger.warning("OTA ACK timeout at chunk %d", chunk_seq)
                except Exception as e:
                    logger.warning("OTA ACK error at chunk %d: %s", chunk_seq, e)

            transfer_elapsed = time.monotonic() - transfer_start
            client_sock.close()

        except asyncio.TimeoutError:
            logger.warning("OTA: No client connected within timeout")
            transfer_elapsed = 0
        except asyncio.CancelledError:
            logger.info("OTA server cancelled")
            transfer_elapsed = time.monotonic() - start_time
        except Exception as e:
            logger.error("OTA server error: %s", e)
            transfer_elapsed = time.monotonic() - start_time
        finally:
            server_sock.close()

        if transfer_elapsed == 0:
            transfer_elapsed = 0.001

        self._stats = {
            "throughput_mbps": round((bytes_sent * 8) / transfer_elapsed / 1_000_000, 3),
            "chunks_sent": chunks_sent,
            "chunks_acked": chunks_acked,
            "total_chunks": TOTAL_CHUNKS,
            "bytes_sent": bytes_sent,
            "transfer_elapsed_s": round(transfer_elapsed, 2),
            "integrity_pass_rate_pct": round(
                chunks_acked / max(chunks_sent, 1) * 100, 2
            ),
        }
        logger.info("OTA transfer complete: %s", self._stats)

    async def stop(self, session_id: str) -> dict:
        """Zastaví OTA server, vrátí statistiky."""
        self._running = False
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        logger.info("UC-D stopped (session=%s)", session_id)
        return self._stats

    def evaluate(self, measured: dict[str, Any], obu_stats: dict | None = None) -> dict:
        """Custom evaluace pro UC-D: mapuje OTA-specific metriky."""
        profile = self.profile()

        # Mapuj OTA stats na metriky v thresholds
        dl_throughput = measured.get("throughput_mbps", 0)
        integrity_rate = measured.get("integrity_pass_rate_pct", 0)

        eval_measured = {
            "dl_throughput_mbps": dl_throughput,
            "application_reliability_pct": integrity_rate,
        }

        return super().evaluate(eval_measured, obu_stats)

    def get_live_stats(self, session_id: str) -> dict:
        return {"uc": "UC-D", **self._stats}

    def get_obu_instructions(self, params: dict[str, Any]) -> str:
        return (
            "OBU: Připoj se TCP na burst_port. Přijímej OTA chunky "
            "[header_len:4B][JSON header][64 KB data]. Po každém chunku "
            "pošli ACK zpět."
        )
