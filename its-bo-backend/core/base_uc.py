"""
BaseUseCase – Abstraktní třída a UCProfile dataclass pro UC plugin systém.

Každý UC plugin MUSÍ implementovat BaseUseCase a definovat svůj UCProfile.

UCProfile je frozen (immutable) – normativní prahy nemohou být přepsány
za runtime. Toto je záměr: value = threshold definovaný standardem.

evaluate() má defaultní implementaci: porovnává measured vs. thresholds
z profilu. Plugin může přepsat pokud potřebuje custom evaluaci.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import logging

logger = logging.getLogger("itsbo.core.base_uc")


@dataclass(frozen=True)
class UCProfile:
    """
    Immutable profil use case.

    Thresholds jsou frozen – nelze měnit za runtime.
    Každý threshold mapuje metriku na {value, op, ref} kde:
    - value: normativní hodnota
    - op: porovnávací operátor ("<=", ">=", "==")
    - ref: odkaz na specifický requirement v standardu (např. "R.5.4-004")
    """

    id: str                        # "UC-A"
    name: str                      # "Extended Sensors / SDSM"
    standard_ref: str              # "3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-004]"
    description: str
    communication_pattern: str     # "UL_ONLY" | "DL_ONLY" | "BIDIRECTIONAL" | "BIDIRECTIONAL_ASYMMETRIC"
    ul_transport: str              # "burst_udp" | "app_cpm" | "app_video" | "none"
    dl_transport: str              # "app_control" | "app_video" | "app_ota" | "burst_udp" | "app_cpm_aggregated" | "none"
    thresholds: dict[str, dict[str, Any]]  # immutable referenční prahy
    default_params: dict[str, Any]         # výchozí parametry (přepsatelné effective_params)
    baseline_required: bool        # True = spustit baseline před testem
    min_repetitions: int           # Doporučený minimální počet opakování (lab: 3, field: 5)
    default_duration_s: int        # Výchozí délka testu v sekundách


class BaseUseCase(ABC):
    """
    Abstraktní třída pro UC pluginy.

    Každý plugin MUSÍ implementovat: profile, start, stop, get_live_stats,
    get_obu_instructions.

    evaluate() má defaultní implementaci – porovnává measured vs. thresholds.
    Plugin může override pokud potřebuje custom evaluaci.
    """

    @abstractmethod
    def profile(self) -> UCProfile:
        """Vrátí immutable profil UC s normativními prahy."""
        ...

    @abstractmethod
    async def start(
        self,
        params: dict[str, Any],
        session_id: str,
        ports: dict[str, int],
        obu_ip: str,
    ) -> None:
        """
        Spustí UC chování.

        Args:
            params: effective_params (merged default + custom).
            session_id: server-generated session ID.
            ports: {"burst_port": int, "control_port": int}.
            obu_ip: IP adresa OBU.
        """
        ...

    @abstractmethod
    async def stop(self, session_id: str) -> dict:
        """
        Čistě ukončí všechny transporty a tasks.

        Returns:
            dict: server-side statistiky (throughput, loss, RTT, ...).
        """
        ...

    @abstractmethod
    def get_live_stats(self, session_id: str) -> dict:
        """
        Live metriky pro SSE feed (voláno každou sekundu).

        Returns:
            dict: odlehčené metriky pro real-time zobrazení.
        """
        ...

    def evaluate(
        self,
        measured: dict[str, Any],
        obu_stats: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Defaultní evaluace: pro každý threshold porovná measured hodnotu.

        obu_stats: pokud OBU poslal stats v session/stop, použijí se
        pro packet_delivery_ratio výpočet.

        Returns:
            dict: {
                "evaluation": {metric: {measured, threshold, op, pass, ref}},
                "overall_pass": bool,
                "packet_delivery_ratio_pct": float | None,
                "interpretation": str
            }
        """
        profile = self.profile()
        evaluation: dict[str, dict] = {}
        all_pass = True

        for metric, thresh in profile.thresholds.items():
            val = measured.get(metric)
            if val is None:
                evaluation[metric] = {
                    "measured": None,
                    "threshold": thresh["value"],
                    "op": thresh["op"],
                    "pass": False,
                    "ref": thresh["ref"],
                    "note": "metric not measured",
                }
                all_pass = False
                continue

            op = thresh["op"]
            if op == "<=":
                passed = val <= thresh["value"]
            elif op == ">=":
                passed = val >= thresh["value"]
            else:
                passed = val == thresh["value"]

            evaluation[metric] = {
                "measured": val,
                "threshold": thresh["value"],
                "op": op,
                "pass": passed,
                "ref": thresh["ref"],
            }
            if not passed:
                all_pass = False

        # Packet delivery ratio (OBU sent vs. ITS-BO received)
        pdr: Optional[float] = None
        if obu_stats and "packets_sent" in obu_stats and "packets_received" in measured:
            sent = obu_stats["packets_sent"]
            if sent > 0:
                pdr = round(measured["packets_received"] / sent * 100, 4)

        interpretation = self._generate_interpretation(evaluation, all_pass, measured)

        return {
            "evaluation": evaluation,
            "overall_pass": all_pass,
            "packet_delivery_ratio_pct": pdr,
            "interpretation": interpretation,
        }

    def _generate_interpretation(
        self,
        evaluation: dict,
        all_pass: bool,
        measured: dict,
    ) -> str:
        """Generuje srozumitelný textový závěr pro diplomku."""
        profile = self.profile()
        if all_pass:
            return (
                f"PASS – Síť splňuje všechny požadavky {profile.id} "
                f"({profile.name}) dle {profile.standard_ref}."
            )
        fails = [
            f"{m}: naměřeno {e['measured']}, požadavek {e['op']} {e['threshold']} [{e['ref']}]"
            for m, e in evaluation.items()
            if not e["pass"]
        ]
        return (
            f"FAIL – Síť nesplňuje {profile.id} požadavky. "
            f"Nesplněné metriky: {'; '.join(fails)}."
        )

    @abstractmethod
    def get_obu_instructions(self, params: dict[str, Any]) -> str:
        """Instrukce pro OBU app – co má dělat po session/start."""
        ...
