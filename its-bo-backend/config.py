"""
Centrální konfigurace ITS-BO Test Platform.

Hodnoty se berou z env vars, s rozumnými defaults.
Při terénním nasazení na VPS se změní jen SERVER_BIND_IP.
Při lab nasazení (Amarisoft Callbox) se přidá statická route.

Klíčové hodnoty:
- UDP_RECV_BUFFER_BYTES = 4 MB – KRITICKÉ pro BurstReceiver při 25 Mbps
  bez ztrát. Kernel default (512 KB) nestačí.
- Port ranges: burst 5100-5199, control 4500-4599 – dynamicky
  přidělované per session přes PortAllocator.
"""
import os

# ──────────────────────────────────────────────────────────
# Síťová konfigurace
# ──────────────────────────────────────────────────────────
SERVER_BIND_IP: str = os.getenv("ITSBO_BIND_IP", "0.0.0.0")
API_PORT: int = int(os.getenv("ITSBO_API_PORT", "8000"))
FRONTEND_PORT: int = int(os.getenv("ITSBO_FRONTEND_PORT", "3000"))

# ──────────────────────────────────────────────────────────
# Dynamické porty – rozsahy pro per-session alokaci
# ──────────────────────────────────────────────────────────
BURST_PORT_RANGE_START: int = int(os.getenv("ITSBO_BURST_PORT_START", "5100"))
BURST_PORT_RANGE_END: int = int(os.getenv("ITSBO_BURST_PORT_END", "5199"))
CONTROL_PORT_RANGE_START: int = int(os.getenv("ITSBO_CONTROL_PORT_START", "4500"))
CONTROL_PORT_RANGE_END: int = int(os.getenv("ITSBO_CONTROL_PORT_END", "4599"))
BASELINE_PORT: int = int(os.getenv("ITSBO_BASELINE_PORT", "5200"))

# ──────────────────────────────────────────────────────────
# UDP buffer – KRITICKÉ pro příjem 25 Mbps bez ztrát
# ──────────────────────────────────────────────────────────
UDP_RECV_BUFFER_BYTES: int = int(os.getenv("ITSBO_UDP_RECV_BUF", "4194304"))  # 4 MB

# ──────────────────────────────────────────────────────────
# Test defaults
# ──────────────────────────────────────────────────────────
DEFAULT_TEST_DURATION_S: int = int(os.getenv("ITSBO_DEFAULT_DURATION", "60"))
SESSION_TIMEOUT_S: int = int(os.getenv("ITSBO_SESSION_TIMEOUT", "300"))
NO_PACKET_TIMEOUT_S: int = int(os.getenv("ITSBO_NO_PACKET_TIMEOUT", "10"))

# ──────────────────────────────────────────────────────────
# Cesty
# ──────────────────────────────────────────────────────────
RESULTS_DIR: str = os.getenv("ITSBO_RESULTS_DIR", "results")
LOGS_DIR: str = os.getenv("ITSBO_LOGS_DIR", "logs")

# ──────────────────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────────────────
CORS_ORIGINS: list[str] = ["*"]  # Lab prostředí, žádná autentizace
