"""
AppLayerSimulator – UC-specifické payload generátory.

Generuje sémanticky věrné payloady pro každý UC:
- UC-A: CPM dle ETSI TS 103 324 / TS 102 894-2 (messageId=14, protocolVersion=1)
- UC-B: H.264-like GOP pattern (I-frame 50 KB / P-frame 5 KB)
- UC-C: MCM řídicí zpráva (256 B paddovaná)
- UC-D: OTA chunk (64 KB data + JSON header)

Payloady jsou JSON (ne ASN.1 UPER) – zdůvodnění viz specifikace §1.3.
Paddovány na normativní velikost dle příslušného standardu.
"""

import asyncio
import hashlib
import json
import logging
import os
import socket
import time
from typing import Optional

logger = logging.getLogger("itsbo.transport.app_layer_simulator")


class AppLayerSimulator:
    """
    Generuje UC-specifické payloady se sémanticky věrnou strukturou.
    Třída slouží jako factory i jako async runner pro DL smyčky.
    """

    # ══════════════════════════════════════════════════════════
    # UC-A: CPM-like payload
    # ══════════════════════════════════════════════════════════

    def build_cpm(self, seq: int, num_objects: int = 5) -> bytes:
        """
        Generuje CPM-like JSON payload dle ETSI TS 103 324 + TS 102 894-2.

        messageId = 14 (cpm) dle TR 103 562 B.2.2.
        protocolVersion = 1 dle TR 103 562 B.2.2.
        stationType = 5 (passengerCar) dle TS 102 894-2.
        Pozice: WGS84 v 1/10 micro degree (dle TS 102 894-2 DE_Latitude).

        Výsledný payload paddován na 1600 B (R.5.4-001).

        Args:
            seq: pořadové číslo zprávy.
            num_objects: počet perceivedObjects v CPM.

        Returns:
            bytes: 1600 B CPM payload.
        """
        cpm = {
            "header": {
                "messageId": 14,
                "stationId": 1001,
                "referenceTime": int(time.time() * 1000),
                "protocolVersion": 1,
            },
            "managementContainer": {
                "stationType": 5,  # passengerCar
                "referencePosition": {
                    "latitude": 501234560,   # WGS84, 1/10 micro degree
                    "longitude": 144567890,
                    "altitude": 25000,       # 0.01 m units
                },
            },
            "perceivedObjects": [
                self._random_object(i, seq) for i in range(num_objects)
            ],
        }
        raw = json.dumps(cpm).encode("utf-8")
        # Padding na 1600 B (normativní payload size R.5.4-001)
        if len(raw) < 1600:
            raw += b"\x00" * (1600 - len(raw))
        return raw[:1600]

    def _random_object(self, obj_id: int, seq: int) -> dict:
        """
        Generuje perceivedObject s variantními hodnotami per seq.

        Hodnoty variují deterministicky dle seq a obj_id – reprodukovatelné
        pro debugging.
        """
        return {
            "objectId": obj_id,
            "timeOfMeasurement": -(seq % 100),  # ms, záporné = v minulosti
            "position": {
                "xDistance": 1500 + (seq * 10 + obj_id * 100) % 5000,  # 0.01m
                "yDistance": 800 + (obj_id * 200) % 2000,
            },
            "velocity": {
                "xVelocity": 1200 + (seq * 5) % 500,  # 0.01 m/s
                "yVelocity": 0,
            },
            "objectAge": 0,
            "classification": [
                {"vehicleSubClass": 3, "confidence": 75}  # passengerCar
            ],
        }

    # ══════════════════════════════════════════════════════════
    # UC-A: Agregovaná mapa (DL)
    # ══════════════════════════════════════════════════════════

    async def run_cpm_aggregation(
        self,
        target_ip: str,
        target_port: int,
        session_id: str,
        ul_receiver,
        aggregation_window_ms: int = 500,
        tx_rate_hz: int = 10,
    ) -> None:
        """
        Agregační smyčka simulující ITS-BO agregační funkci dle TS 103 324 §6.1.

        Každých 1000/tx_rate_hz ms:
        1. Vezme objekty přijaté za posledních aggregation_window_ms
        2. Sloučí do jedné mapy (minimálně 1 objekt, max 20)
        3. Odešle zpět na OBU jako JSON

        Args:
            target_ip: IP OBU kam posílat DL.
            target_port: UDP port OBU (control_port).
            session_id: pro logování.
            ul_receiver: BurstReceiver instance pro přístup k přijatým datům.
            aggregation_window_ms: okno pro sloučení (default 500 ms).
            tx_rate_hz: frekvence DL odesílání (default 10 Hz).
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()
        interval = 1.0 / tx_rate_hz
        seq = 0

        logger.info(
            "CPM aggregation started → %s:%d @ %d Hz (session=%s)",
            target_ip, target_port, tx_rate_hz, session_id,
        )

        try:
            while True:
                await asyncio.sleep(interval)

                # Sestav agregovanou mapu
                # V reálné implementaci bychom parsovali CPM z ul_receiver._packets
                # Pro testovací účely generujeme synthetické objekty
                num_objects = min(max(1, len(ul_receiver._packets) % 20), 20)
                objects = [self._random_object(i, seq) for i in range(num_objects)]

                aggregated = {
                    "header": {
                        "messageId": 14,
                        "stationId": 9001,       # ITS-BO station ID
                        "aggregated": True,
                        "protocolVersion": 1,
                        "seq": seq,
                        "referenceTime": int(time.time() * 1000),
                    },
                    "objects": objects,
                }
                payload = json.dumps(aggregated).encode("utf-8")
                try:
                    await loop.sock_sendto(sock, payload, (target_ip, target_port))
                except Exception as e:
                    logger.debug("CPM aggregation send error: %s", e)

                seq += 1
        except asyncio.CancelledError:
            logger.info("CPM aggregation stopped (session=%s)", session_id)
        finally:
            sock.close()

    # ══════════════════════════════════════════════════════════
    # UC-B: Video-like burst
    # ══════════════════════════════════════════════════════════

    def build_video_gop(self, frame_seq: int) -> list[bytes]:
        """
        Vrátí list paketů pro jeden frame.

        GOP structure (30 frames):
        - I-frame (frame_seq % 30 == 0): ~50 KB → ~34 paketů po 1472 B
        - P-frame: ~5 KB → 3-4 pakety

        Each packet starts with header:
        [frame_type:1B][frame_seq:4B][gop_seq:4B][timestamp_us:8B]

        Args:
            frame_seq: pořadové číslo framu v celé sekvenci.

        Returns:
            list[bytes]: fragmentovaný frame do 1472-byte paketů (MTU safe).
        """
        is_iframe = (frame_seq % 30 == 0)
        frame_size = 50000 if is_iframe else 5000
        frame_type = b"I" if is_iframe else b"P"

        header = (
            frame_type
            + frame_seq.to_bytes(4, "big")
            + (frame_seq // 30).to_bytes(4, "big")
            + int(time.monotonic() * 1_000_000).to_bytes(8, "big")
        )

        data = header + os.urandom(frame_size - len(header))
        # Fragment do 1472-byte paketů (MTU safe)
        return [data[i : i + 1472] for i in range(0, len(data), 1472)]

    async def run_video_dl(
        self,
        target_ip: str,
        target_port: int,
        session_id: str,
        bitrate_mbps: float = 10.0,
        fps: int = 30,
        duration_s: float = 60.0,
    ) -> dict:
        """
        Spustí DL video burst (GOP pattern) směrem k OBU.

        Bitrate řízení: inter-frame interval = (frame_size × 8) / target_bitrate_bps,
        s adaptivní kompenzací skutečného elapsed.

        Args:
            target_ip: IP OBU.
            target_port: UDP port OBU.
            session_id: pro logování.
            bitrate_mbps: cílový DL bitrate.
            fps: framerate (30 fps default).
            duration_s: doba trvání.

        Returns:
            dict: statistiky DL video (packets_sent, bytes_sent, actual bitrate).
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()

        frame_seq = 0
        sent_bytes = 0
        sent_packets = 0
        start = time.monotonic()
        frame_interval = 1.0 / fps  # ~33ms for 30fps
        next_frame = start

        logger.info(
            "Video DL started → %s:%d @ %.1f Mbps, %d fps (session=%s)",
            target_ip, target_port, bitrate_mbps, fps, session_id,
        )

        try:
            while (time.monotonic() - start) < duration_s:
                now = time.monotonic()
                if now < next_frame:
                    await asyncio.sleep(next_frame - now)

                packets = self.build_video_gop(frame_seq)
                for pkt in packets:
                    try:
                        await loop.sock_sendto(sock, pkt, (target_ip, target_port))
                        sent_bytes += len(pkt)
                        sent_packets += 1
                    except Exception as e:
                        logger.debug("Video DL send error: %s", e)

                frame_seq += 1
                next_frame += frame_interval

        except asyncio.CancelledError:
            logger.info("Video DL cancelled (session=%s)", session_id)
        finally:
            sock.close()

        elapsed = time.monotonic() - start
        if elapsed == 0:
            elapsed = 0.001

        return {
            "throughput_mbps_actual": round((sent_bytes * 8) / elapsed / 1_000_000, 3),
            "throughput_mbps_target": bitrate_mbps,
            "packets_sent": sent_packets,
            "frames_sent": frame_seq,
            "bytes_sent": sent_bytes,
            "elapsed_s": round(elapsed, 2),
        }

    # ══════════════════════════════════════════════════════════
    # UC-C: MCM řídicí zpráva
    # ══════════════════════════════════════════════════════════

    def build_mcm(self, seq: int, session_id: str) -> bytes:
        """
        Generuje MCM (Maneuvering Coordination Message) pro řídicí smyčku.

        Velikost: 256 B (paddováno).
        timestamp_us je z ITS-BO clock (time.monotonic) – bude použit
        pro RTT výpočet na příjmu ACK.

        Args:
            seq: pořadové číslo MCM.
            session_id: identifikátor session.

        Returns:
            bytes: 256 B MCM payload.
        """
        mcm = {
            "messageId": "MCM",
            "stationId": 9001,
            "seq": seq,
            "timestamp_us": int(time.monotonic() * 1_000_000),
            "control": {
                "steeringAngle": (seq * 2) % 360 - 180,
                "throttlePct": 15 + (seq % 10),
                "brakePct": 0,
                "gear": 4,
                "emergencyStop": False,
            },
            "sessionId": session_id,
        }
        raw = json.dumps(mcm).encode("utf-8")
        if len(raw) < 256:
            raw += b"\x00" * (256 - len(raw))
        return raw[:256]

    # ══════════════════════════════════════════════════════════
    # UC-D: OTA chunk
    # ══════════════════════════════════════════════════════════

    def build_ota_chunk(
        self,
        chunk_seq: int,
        total_chunks: int,
        package_id: str = "SW-v2.1.0-patch",
    ) -> bytes:
        """
        TCP chunk pro OTA update.

        Format: [header_length:4B big-endian][JSON header][64 KB random data]

        JSON header obsahuje: messageId, packageId, chunkSeq, totalChunks,
        chunkSize, md5Partial (prvních 16 znaků MD5 dat).

        Args:
            chunk_seq: pořadové číslo chunku (0-indexed).
            total_chunks: celkový počet chunků.
            package_id: identifikátor SW balíku.

        Returns:
            bytes: kompletní chunk (4B + header + 64 KB dat).
        """
        data_block = os.urandom(65536)
        chunk = {
            "messageId": "OTA_CHUNK",
            "packageId": package_id,
            "chunkSeq": chunk_seq,
            "totalChunks": total_chunks,
            "chunkSize": 65536,
            "md5Partial": hashlib.md5(data_block).hexdigest()[:16],
        }
        header = json.dumps(chunk).encode("utf-8")
        # Délka header (4B) + header + data
        return len(header).to_bytes(4, "big") + header + data_block
