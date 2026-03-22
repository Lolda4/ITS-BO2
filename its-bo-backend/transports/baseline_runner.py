"""
BaselineRunner – Referenční baseline měření.

Spouští se před testovací session (pokud UC má baseline_required = True).
OBU iniciuje baseline přes POST /api/v1/baseline/start.

Zjednodušená implementace: 10× ICMP ping. UDP burst baseline je
komplikovaný (vyžaduje koordinaci se serverem pro receiver), proto
používáme jen ping. iPerf3 jako volitelný external baseline je
doporučen v diplomce.

Baseline slouží jako referenční kontext pro interpretaci výsledků –
pokud baseline ping je 15 ms, pak změřený RTT 16 ms v testu má jinou
interpretaci než RTT 16 ms s baseline pingem 5 ms.
"""

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger("itsbo.transport.baseline_runner")


class BaselineRunner:
    """
    Referenční baseline měření (ICMP ping).

    Spouští subprocess pro ping – nepoužívá raw ICMP socket,
    protože raw socket vyžaduje root a ping binary je obecně
    dostupný na všech Linux systémech.
    """

    async def run_ping_baseline(self, obu_ip: str, count: int = 10) -> dict:
        """
        Provede ICMP ping baseline: `count` × ping s 200ms intervalem.

        Parsuje výstup ping příkazu pro avg/min/max/mdev RTT.

        Args:
            obu_ip: IP adresa OBU pro ping.
            count: počet ping paketů (default 10).

        Returns:
            dict: {status, ping_rtt_min_ms, ping_rtt_avg_ms,
                   ping_rtt_max_ms, ping_rtt_mdev_ms}
                  nebo {status: "failed"/"no_response", error: str}
        """
        logger.info("Starting ping baseline to %s (%d packets)", obu_ip, count)

        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", str(count), "-i", "0.2", "-W", "1", obu_ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=count * 2 + 5
            )
            output = stdout.decode()

            # Hledáme "rtt min/avg/max/mdev = X/Y/Z/W ms"
            for line in output.split("\n"):
                if "avg" in line and "/" in line:
                    # Formát: rtt min/avg/max/mdev = 8.123/9.456/14.234/1.567 ms
                    match = re.search(
                        r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", line
                    )
                    if match:
                        result = {
                            "status": "completed",
                            "ping_rtt_min_ms": float(match.group(1)),
                            "ping_rtt_avg_ms": float(match.group(2)),
                            "ping_rtt_max_ms": float(match.group(3)),
                            "ping_rtt_mdev_ms": float(match.group(4)),
                        }
                        logger.info(
                            "Ping baseline completed: avg=%.1f ms, min=%.1f ms, max=%.1f ms",
                            result["ping_rtt_avg_ms"],
                            result["ping_rtt_min_ms"],
                            result["ping_rtt_max_ms"],
                        )
                        return result

            # Ping proběhl ale nenašli jsme RTT řádek = žádná odpověď
            logger.warning("Ping to %s completed but no response received", obu_ip)
            return {"status": "no_response", "raw_output": output[:500]}

        except asyncio.TimeoutError:
            logger.error("Ping baseline to %s timed out", obu_ip)
            return {"status": "failed", "error": "timeout"}
        except FileNotFoundError:
            logger.error("ping command not found")
            return {"status": "failed", "error": "ping command not found"}
        except Exception as e:
            logger.error("Ping baseline error: %s", e)
            return {"status": "failed", "error": str(e)}

    async def run_burst_baseline(
        self,
        port: int,
        duration_s: float = 5.0,
    ) -> dict:
        """
        Připraví UDP burst receiver pro baseline.
        OBU pošle burst, ITS-BO měří throughput a loss.

        Toto je volitelný rozšířený baseline – v základní implementaci
        stačí ping baseline.

        Returns:
            dict: placeholder pro budoucí implementaci.
        """
        logger.info("Burst baseline receiver ready on port %d (not implemented, using ping only)", port)
        return {
            "status": "skipped",
            "note": "Burst baseline not implemented, using ping baseline only",
        }
