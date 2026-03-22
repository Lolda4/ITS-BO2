"""
PreflightChecker – Pre-flight validace před každým testem.

Před každým testem ověří readiness infrastruktury:
1. Ping OBU IP (max 1s timeout)
2. Alokované porty volné
3. Results directory zapisovatelný
4. Disk space > 100 MB

Výsledek je součástí session/init response jako preflight_warnings.
Varování neblokují test – tester rozhoduje.
"""

import asyncio
import logging
import os
import shutil
import socket

from config import RESULTS_DIR

logger = logging.getLogger("itsbo.core.preflight")


class PreflightChecker:
    """
    Pre-flight kontroly před spuštěním testu.

    Žádná kontrola neblokuje test – vše se vrací jako warnings
    s úrovní "warning" nebo "error". Tester rozhoduje zda pokračovat.
    """

    async def check(self, obu_ip: str, ports: dict[str, int]) -> list[dict]:
        """
        Provede všechny pre-flight kontroly.

        Args:
            obu_ip: IP adresa OBU pro ping.
            ports: alokované porty {"burst_port": int, "control_port": int}.

        Returns:
            list[dict]: seznam varování [{level: str, msg: str}].
                        Prázdný list = vše OK.
        """
        warnings: list[dict] = []

        # 1. Ping OBU IP (max 1s timeout)
        if not await self._ping(obu_ip, timeout_s=1):
            warnings.append({
                "level": "warning",
                "msg": f"OBU IP {obu_ip} neodpovídá na ping (může být filtrovaný)",
            })

        # 2. Alokované porty volné
        for name, port in ports.items():
            if not self._port_free(port):
                warnings.append({
                    "level": "error",
                    "msg": f"Port {port} ({name}) je obsazený",
                })

        # 3. Results directory zapisovatelný
        os.makedirs(RESULTS_DIR, exist_ok=True)
        if not os.access(RESULTS_DIR, os.W_OK):
            warnings.append({
                "level": "error",
                "msg": f"Results directory '{RESULTS_DIR}' není zapisovatelný",
            })

        # 4. Disk space > 100 MB
        try:
            free_mb = shutil.disk_usage(RESULTS_DIR).free / 1024 / 1024
            if free_mb < 100:
                warnings.append({
                    "level": "warning",
                    "msg": f"Málo místa na disku: {free_mb:.0f} MB",
                })
        except Exception:
            warnings.append({
                "level": "warning",
                "msg": "Nelze číslit místo na disku",
            })

        if warnings:
            logger.warning("Preflight warnings: %s", warnings)
        else:
            logger.info("Preflight checks passed for OBU %s", obu_ip)

        return warnings

    async def _ping(self, ip: str, timeout_s: float = 1.0) -> bool:
        """
        Zkusí pingout IP adresu.

        Args:
            ip: IP adresa pro ping.
            timeout_s: timeout v sekundách.

        Returns:
            bool: True pokud alespoň jeden ping prošel.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", str(int(timeout_s)), ip,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 1)
            return proc.returncode == 0
        except Exception:
            return False

    def _port_free(self, port: int) -> bool:
        """
        Ověří zda je UDP port volný (není obsazený jiným procesem).

        Args:
            port: číslo portu.

        Returns:
            bool: True pokud port je volný.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", port))
            sock.close()
            return True
        except OSError:
            return False
