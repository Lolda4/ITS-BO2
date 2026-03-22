#!/usr/bin/env python3
"""
test_transport.py – OBU simulátor pro smoke testování ITS-BO backendu.

Simuluje OBU klienta: provede kompletní session handshake a datový
přenos bez potřeby Android telefonu.

Použití:
    python test_transport.py <server_ip> <uc_id> [--duration 5]

Příklady:
    python test_transport.py 127.0.0.1 UC-A --duration 5
    python test_transport.py 192.168.0.161 UC-C --duration 10
    python test_transport.py 127.0.0.1 UC-D --duration 15

Co dělá:
    1. POST /api/v1/session/init → session_id + allocated_ports
    2. POST /api/v1/session/start
    3. Datový přenos dle UC:
       - UC-A: posílá CPM pakety na burst_port (10 Hz)
       - UC-B: posílá video burst na burst_port (10 Mbps)
       - UC-C: posílá UDP burst na burst_port (25 Mbps) +
               přijímá MCM na control_port+1000 a odesílá ACK
       - UC-D: připojí se TCP na burst_port, přijímá OTA chunky, posílá ACK
    4. POST /api/v1/session/stop s obu_stats
    5. Vypíše výsledek
"""

import argparse
import asyncio
import json
import os
import socket
import struct
import sys
import time
import zlib
from typing import Optional

# HTTP client (stdlib, žádné extra dependencies)
import urllib.request
import urllib.error


def http_post(url: str, data: dict) -> dict:
    """HTTP POST s JSON body, vrátí JSON response."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"HTTP Error {e.code}: {error_body}")
        sys.exit(1)


def http_get(url: str) -> dict:
    """HTTP GET, vrátí JSON response."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def build_rfc_packet(seq: int, uc_id_num: int, session_hash: int, size: int = 1600) -> bytes:
    """Sestaví paket s RFC 5357-style binary header."""
    buf = bytearray(size)
    struct.pack_into(">I", buf, 0, seq & 0xFFFFFFFF)           # seq: 4B
    struct.pack_into(">Q", buf, 4, int(time.monotonic() * 1e9))  # timestamp_ns: 8B
    struct.pack_into(">H", buf, 12, uc_id_num)                  # uc_id: 2B
    struct.pack_into(">I", buf, 14, session_hash)                # session_hash: 4B
    return bytes(buf)


def session_id_to_hash(session_id: str) -> int:
    """CRC32 hash session_id pro packet header."""
    return zlib.crc32(session_id.encode()) & 0xFFFFFFFF


UC_ID_MAP = {"UC-A": 1, "UC-B": 2, "UC-C": 3, "UC-D": 4}


# ══════════════════════════════════════════════════════════
# UC-A: CPM burst
# ══════════════════════════════════════════════════════════
async def run_uc_a(server_ip: str, burst_port: int, control_port: int,
                    session_id: str, duration_s: float) -> dict:
    """Posílá CPM-like pakety 1600 B @ 10 Hz."""
    print(f"  UC-A: Sending CPM packets → {server_ip}:{burst_port} @ 10 Hz...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    session_hash = session_id_to_hash(session_id)
    seq = 0
    sent_bytes = 0
    start = time.monotonic()
    interval = 0.1  # 10 Hz

    while time.monotonic() - start < duration_s:
        pkt = build_rfc_packet(seq, UC_ID_MAP["UC-A"], session_hash, 1600)
        sock.sendto(pkt, (server_ip, burst_port))
        sent_bytes += len(pkt)
        seq += 1
        await asyncio.sleep(interval)

    sock.close()
    elapsed = time.monotonic() - start
    print(f"  UC-A: Sent {seq} packets ({sent_bytes / 1024:.0f} KB) in {elapsed:.1f}s")
    return {"packets_sent": seq, "bytes_sent": sent_bytes}


# ══════════════════════════════════════════════════════════
# UC-B: Video burst
# ══════════════════════════════════════════════════════════
async def run_uc_b(server_ip: str, burst_port: int, control_port: int,
                    session_id: str, duration_s: float) -> dict:
    """Posílá video-like burst @ ~10 Mbps."""
    print(f"  UC-B: Sending video burst → {server_ip}:{burst_port} @ ~10 Mbps...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    session_hash = session_id_to_hash(session_id)
    seq = 0
    sent_bytes = 0
    start = time.monotonic()
    target_bps = 10_000_000  # 10 Mbps
    pkt_size = 1472
    interval = (pkt_size * 8) / target_bps

    while time.monotonic() - start < duration_s:
        pkt = build_rfc_packet(seq, UC_ID_MAP["UC-B"], session_hash, pkt_size)
        sock.sendto(pkt, (server_ip, burst_port))
        sent_bytes += len(pkt)
        seq += 1
        await asyncio.sleep(interval)

    sock.close()
    elapsed = time.monotonic() - start
    actual_mbps = (sent_bytes * 8) / elapsed / 1_000_000 if elapsed > 0 else 0
    print(f"  UC-B: Sent {seq} packets ({sent_bytes / 1024 / 1024:.1f} MB, {actual_mbps:.1f} Mbps)")
    return {"packets_sent": seq, "bytes_sent": sent_bytes}


# ══════════════════════════════════════════════════════════
# UC-C: UL burst + DL control loop (MCM/ACK)
# ══════════════════════════════════════════════════════════
async def run_uc_c(server_ip: str, burst_port: int, control_port: int,
                    session_id: str, duration_s: float) -> dict:
    """
    Dvě paralelní větve:
    1. UL: UDP burst @ 25 Mbps na burst_port
    2. DL: Přijímá MCM na control_port+1000, odesílá ACK na control_port
    """
    print(f"  UC-C: Starting UL burst + DL control loop...")

    stats = {"packets_sent": 0, "bytes_sent": 0, "mcm_received": 0, "acks_sent": 0}

    async def ul_burst():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        session_hash = session_id_to_hash(session_id)
        seq = 0
        target_bps = 25_000_000
        pkt_size = 1472
        interval = (pkt_size * 8) / target_bps
        start = time.monotonic()

        while time.monotonic() - start < duration_s:
            pkt = build_rfc_packet(seq, UC_ID_MAP["UC-C"], session_hash, pkt_size)
            try:
                sock.sendto(pkt, (server_ip, burst_port))
                stats["bytes_sent"] += len(pkt)
                seq += 1
            except Exception:
                pass
            await asyncio.sleep(interval)

        sock.close()
        stats["packets_sent"] = seq

    async def dl_control():
        # OBU naslouchá na control_port + 1000
        listen_port = control_port + 1000
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", listen_port))
        sock.settimeout(1.0)

        print(f"  UC-C DL: Listening for MCM on port {listen_port}...")
        start = time.monotonic()

        while time.monotonic() - start < duration_s + 2:
            try:
                data, addr = sock.recvfrom(4096)
                recv_ns = int(time.monotonic() * 1e9)

                if len(data) >= 4:
                    # Parse seq z MCM
                    # MCM je JSON s binary header; pro simplicitu
                    # parsujeme prvních 4 bytes jako seq (pokud to je binary)
                    # nebo z JSON
                    mcm_seq = 0
                    try:
                        # Zkus JSON parse
                        json_str = data.decode("utf-8").rstrip("\x00")
                        mcm_json = json.loads(json_str)
                        mcm_seq = mcm_json.get("seq", 0)
                    except Exception:
                        mcm_seq = int.from_bytes(data[0:4], "big")

                    stats["mcm_received"] += 1

                    # Odešli ACK: [seq:4B][0xAC:1B][processing_ns:8B]
                    processing_ns = int(time.monotonic() * 1e9) - recv_ns
                    ack = bytearray(13)
                    struct.pack_into(">I", ack, 0, mcm_seq)
                    ack[4] = 0xAC
                    struct.pack_into(">Q", ack, 5, processing_ns)

                    sock.sendto(bytes(ack), (server_ip, control_port))
                    stats["acks_sent"] += 1

            except socket.timeout:
                continue
            except Exception as e:
                if time.monotonic() - start < duration_s:
                    pass  # ignoruj errory uprostřed testu
                break

        sock.close()

    # Spusť obě větve paralelně
    await asyncio.gather(ul_burst(), dl_control())

    print(f"  UC-C: UL sent {stats['packets_sent']} pkts, DL received {stats['mcm_received']} MCMs, sent {stats['acks_sent']} ACKs")
    return {"packets_sent": stats["packets_sent"], "bytes_sent": stats["bytes_sent"]}


# ══════════════════════════════════════════════════════════
# UC-D: TCP OTA receiver
# ══════════════════════════════════════════════════════════
async def run_uc_d(server_ip: str, burst_port: int, control_port: int,
                    session_id: str, duration_s: float) -> dict:
    """Připojí se TCP na burst_port, přijímá OTA chunky, posílá ACK."""
    print(f"  UC-D: Connecting TCP to {server_ip}:{burst_port}...")

    loop = asyncio.get_event_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((server_ip, burst_port))
    except Exception as e:
        print(f"  UC-D: Connection failed: {e}")
        return {"packets_sent": 0, "bytes_sent": 0}

    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    chunks_received = 0
    bytes_received = 0
    start = time.monotonic()

    try:
        while time.monotonic() - start < duration_s:
            # Přijmi header length (4B)
            header_len_bytes = b""
            while len(header_len_bytes) < 4:
                chunk = sock.recv(4 - len(header_len_bytes))
                if not chunk:
                    break  # connection closed
                header_len_bytes += chunk

            if len(header_len_bytes) < 4:
                break

            header_len = int.from_bytes(header_len_bytes, "big")

            # Přijmi JSON header
            header_data = b""
            while len(header_data) < header_len:
                chunk = sock.recv(header_len - len(header_data))
                if not chunk:
                    break
                header_data += chunk

            # Přijmi data (64 KB)
            try:
                header_json = json.loads(header_data.decode())
                chunk_size = header_json.get("chunkSize", 65536)
            except Exception:
                chunk_size = 65536

            data_block = b""
            while len(data_block) < chunk_size:
                chunk = sock.recv(min(chunk_size - len(data_block), 65536))
                if not chunk:
                    break
                data_block += chunk

            bytes_received += 4 + header_len + len(data_block)
            chunks_received += 1

            # Pošli ACK (4 bytes chunk_seq)
            seq_bytes = chunks_received.to_bytes(4, "big")
            sock.sendall(seq_bytes)

            if chunks_received % 100 == 0:
                elapsed = time.monotonic() - start
                mbps = (bytes_received * 8) / elapsed / 1_000_000 if elapsed > 0 else 0
                print(f"  UC-D: {chunks_received} chunks ({bytes_received / 1024 / 1024:.1f} MB, {mbps:.1f} Mbps)")

    except socket.timeout:
        print("  UC-D: Socket timeout – transfer may be complete")
    except Exception as e:
        print(f"  UC-D: Error: {e}")
    finally:
        sock.close()

    elapsed = time.monotonic() - start
    mbps = (bytes_received * 8) / elapsed / 1_000_000 if elapsed > 0 else 0
    print(f"  UC-D: Received {chunks_received} chunks ({bytes_received / 1024 / 1024:.1f} MB, {mbps:.1f} Mbps)")
    return {"packets_sent": 0, "bytes_sent": 0}  # UC-D je DL_ONLY


# ══════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════
UC_RUNNERS = {
    "UC-A": run_uc_a,
    "UC-B": run_uc_b,
    "UC-C": run_uc_c,
    "UC-D": run_uc_d,
}


async def main():
    parser = argparse.ArgumentParser(
        description="ITS-BO Transport Smoke Test – OBU Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Příklady:
  python test_transport.py 127.0.0.1 UC-A --duration 5
  python test_transport.py 127.0.0.1 UC-C --duration 10
  python test_transport.py 127.0.0.1 UC-D --duration 30
        """,
    )
    parser.add_argument("server_ip", help="IP adresa ITS-BO serveru")
    parser.add_argument("uc_id", choices=["UC-A", "UC-B", "UC-C", "UC-D"],
                        help="Use case ID")
    parser.add_argument("--duration", type=int, default=5,
                        help="Délka testu v sekundách (default: 5)")
    parser.add_argument("--port", type=int, default=8000,
                        help="API port (default: 8000)")

    args = parser.parse_args()
    base_url = f"http://{args.server_ip}:{args.port}"

    print(f"\n{'═' * 60}")
    print(f"  ITS-BO Transport Smoke Test")
    print(f"  Server: {base_url}")
    print(f"  UC: {args.uc_id}")
    print(f"  Duration: {args.duration}s")
    print(f"{'═' * 60}\n")

    # 1. Ověř server
    print("[1/5] Checking server status...")
    try:
        status = http_get(f"{base_url}/api/v1/system/status")
        print(f"  Server online, uptime: {status.get('uptime_human', 'N/A')}")
        print(f"  Plugins: {[p['uc_id'] for p in status.get('plugins', {}).get('loaded', [])]}")
    except Exception as e:
        print(f"  ✗ Server nedostupný: {e}")
        sys.exit(1)

    # 2. Session init
    print(f"\n[2/5] Initializing session...")
    init_data = {
        "uc_id": args.uc_id,
        "obu_ip": "127.0.0.1",  # loopback pro test
        "label": f"Smoke test – {args.uc_id} – {args.duration}s",
        "network_condition": "local_loopback_test",
        "params": {},
        "requested_duration_s": args.duration,
        "obu_app_version": "test_transport.py",
    }
    init_resp = http_post(f"{base_url}/api/v1/session/init", init_data)
    session_id = init_resp["session_id"]
    ports = init_resp["allocated_ports"]
    print(f"  Session ID: {session_id}")
    print(f"  Ports: burst={ports['burst_port']}, control={ports['control_port']}")
    print(f"  Effective params: {json.dumps(init_resp.get('effective_params', {}), indent=4)}")
    warnings = init_resp.get("preflight_warnings", [])
    if warnings:
        print(f"  ⚠ Warnings: {warnings}")

    # 3. Start session
    print(f"\n[3/5] Starting session...")
    start_resp = http_post(f"{base_url}/api/v1/session/start", {"session_id": session_id})
    print(f"  Status: {start_resp.get('status')}")

    # 4. Datový přenos
    print(f"\n[4/5] Running {args.uc_id} transport for {args.duration}s...")
    runner = UC_RUNNERS[args.uc_id]
    obu_stats = await runner(
        server_ip=args.server_ip,
        burst_port=ports["burst_port"],
        control_port=ports["control_port"],
        session_id=session_id,
        duration_s=args.duration,
    )

    # 5. Stop session
    print(f"\n[5/5] Stopping session...")
    stop_data = {
        "session_id": session_id,
        "obu_stats": {
            "packets_sent": obu_stats.get("packets_sent", 0),
            "bytes_sent": obu_stats.get("bytes_sent", 0),
            "send_jitter_ms": 0,
            "max_inter_packet_gap_ms": 0,
            "gc_pause_detected": False,
        },
    }
    result = http_post(f"{base_url}/api/v1/session/stop", stop_data)

    # Výsledek
    print(f"\n{'═' * 60}")
    print(f"  VÝSLEDEK")
    print(f"{'═' * 60}")
    print(f"  Test ID: {result.get('test_id')}")
    print(f"  UC: {result.get('uc_name')}")
    print(f"  Status: {result.get('session_status')}")
    print(f"  Duration: {result.get('duration_actual_s')}s")

    overall_pass = result.get("overall_pass")
    pass_str = "✓ PASS" if overall_pass else "✗ FAIL"
    print(f"\n  Verdict: {pass_str}")
    print(f"  Interpretation: {result.get('interpretation')}")

    if result.get("evaluation"):
        print(f"\n  Evaluation:")
        for metric, ev in result["evaluation"].items():
            m = ev.get("measured", "N/A")
            t = ev.get("threshold", "N/A")
            op = ev.get("op", "?")
            p = "✓" if ev.get("pass") else "✗"
            ref = ev.get("ref", "")
            print(f"    {p} {metric}: {m} {op} {t} [{ref}]")

    pdr = result.get("packet_delivery_ratio_pct")
    if pdr is not None:
        print(f"\n  Packet Delivery Ratio: {pdr}%")

    print(f"\n  Full result saved to: results/{session_id}.json")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
