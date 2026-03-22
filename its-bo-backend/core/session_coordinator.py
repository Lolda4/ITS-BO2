"""
SessionCoordinator – Spravuje životní cyklus sessions.

Session states: INIT → BASELINE → READY → RUNNING → COMPLETED | INTERRUPTED | ERROR

Klíčové zodpovědnosti:
- Generování session_id ve formátu {uc_id}-{YYYYMMDD}-{HHMMSS}-{random4}
- Alokace portů přes PortAllocator
- Pre-flight checks přes PreflightChecker
- Spuštění/zastavení UC pluginu přes PluginLoader
- Timeout detekce: pokud žádný paket > NO_PACKET_TIMEOUT_S → INTERRUPTED
- Evaluace výsledků přes plugin.evaluate()
- Ukládání výsledků přes ResultStore
"""

import asyncio
import logging
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config import (
    DEFAULT_TEST_DURATION_S,
    NO_PACKET_TIMEOUT_S,
    SESSION_TIMEOUT_S,
)
from core.base_uc import BaseUseCase
from core.plugin_loader import PluginLoader
from core.port_allocator import PortAllocator
from core.preflight import PreflightChecker
from core.result_store import ResultStore

logger = logging.getLogger("itsbo.core.session_coordinator")


@dataclass
class SessionState:
    """Mutable state jedné session."""

    session_id: str
    uc_id: str
    state: str  # INIT | BASELINE | READY | RUNNING | COMPLETED | INTERRUPTED | ERROR
    ports: dict[str, int]
    obu_ip: str
    effective_params: dict[str, Any]
    label: str = ""
    network_condition: str = ""
    lab_config: Optional[dict] = None
    obu_app_version: str = ""
    duration_s: int = DEFAULT_TEST_DURATION_S
    start_time: Optional[float] = None  # monotonic
    started_at: Optional[str] = None    # ISO 8601
    last_packet_time: Optional[float] = None  # monotonic – aktualizováno transportem
    interrupt_reason: Optional[str] = None
    error_message: Optional[str] = None
    baseline_data: Optional[dict] = None
    preflight_warnings: list[dict] = field(default_factory=list)
    plugin: Optional[BaseUseCase] = None
    monitor_task: Optional[asyncio.Task] = None


class SessionCoordinator:
    """
    Centrální orchestrátor testovacích sessions.

    Spravuje kompletní lifecycle od init přes start/stop po evaluaci.
    """

    def __init__(
        self,
        plugin_loader: PluginLoader,
        port_allocator: PortAllocator,
        result_store: ResultStore,
    ) -> None:
        self._plugin_loader = plugin_loader
        self._port_allocator = port_allocator
        self._result_store = result_store
        self._preflight = PreflightChecker()
        self.sessions: dict[str, SessionState] = {}

    def _generate_session_id(self, uc_id: str) -> str:
        """
        Generuje session_id ve formátu: {uc_id}-{YYYYMMDD}-{HHMMSS}-{random4}.
        Random suffix zabraňuje kolizi při rychlém spuštění více testů.
        """
        now = datetime.now(timezone.utc)
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{uc_id}-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{rand}"

    async def init_session(
        self,
        uc_id: str,
        obu_ip: str,
        label: str = "",
        network_condition: str = "",
        lab_config: Optional[dict] = None,
        params: Optional[dict] = None,
        requested_duration_s: Optional[int] = None,
        obu_app_version: str = "",
    ) -> dict:
        """
        Inicializuje novou testovací session.

        1. Ověří existenci UC pluginu
        2. Vygeneruje session_id
        3. Alokuje porty (PortAllocator)
        4. Připraví effective_params (merge default + custom)
        5. Provede pre-flight check
        6. Vrátí session_id + allocated_ports + effective_params

        Args:
            uc_id: identifikátor UC ("UC-A", "UC-B", ...).
            obu_ip: IP adresa OBU.
            label: lidsky čitelný popis testu.
            network_condition: popis síťové konfigurace.
            lab_config: lab-specific konfigurace (nepovinné).
            params: custom parametry (přepíší defaults).
            requested_duration_s: požadovaná délka testu.
            obu_app_version: verze OBU app.

        Returns:
            dict: {session_id, server_ready, allocated_ports, effective_params,
                   duration_s, preflight_warnings}

        Raises:
            ValueError: pokud uc_id neexistuje.
            RuntimeError: pokud nejsou volné porty.
        """
        # Ověř plugin
        plugin = self._plugin_loader.get_plugin(uc_id)
        if plugin is None:
            available = self._plugin_loader.available_uc_ids
            raise ValueError(
                f"Unknown UC '{uc_id}'. Available: {available}"
            )

        profile = plugin.profile()
        session_id = self._generate_session_id(uc_id)

        # Alokuj porty
        ports = await self._port_allocator.allocate(session_id)

        # Effective params: merge default + custom
        effective = dict(profile.default_params)
        if params:
            effective.update(params)
        duration = requested_duration_s or profile.default_duration_s
        effective["duration_s"] = duration

        # Pre-flight
        warnings = await self._preflight.check(obu_ip, ports)

        # Vytvoř session state
        session = SessionState(
            session_id=session_id,
            uc_id=uc_id,
            state="INIT",
            ports=ports,
            obu_ip=obu_ip,
            effective_params=effective,
            label=label,
            network_condition=network_condition,
            lab_config=lab_config,
            obu_app_version=obu_app_version,
            duration_s=duration,
            preflight_warnings=warnings,
            plugin=plugin,
        )
        self.sessions[session_id] = session

        logger.info(
            "Session initialized: %s (UC=%s, OBU=%s, ports=%s, duration=%ds)",
            session_id, uc_id, obu_ip, ports, duration,
        )

        return {
            "session_id": session_id,
            "server_ready": True,
            "allocated_ports": ports,
            "effective_params": effective,
            "duration_s": duration,
            "preflight_warnings": warnings,
        }

    async def start_baseline(self, session_id: str, obu_ip: str) -> dict:
        """Připraví backend pro baseline měření."""
        session = self._get_session(session_id)
        session.state = "BASELINE"

        from transports.baseline_runner import BaselineRunner

        runner = BaselineRunner()
        baseline_data = await runner.run_ping_baseline(obu_ip)
        session.baseline_data = baseline_data

        logger.info("Baseline completed for session %s: %s", session_id, baseline_data.get("status"))
        return baseline_data

    async def store_baseline_result(self, session_id: str, baseline_data: dict) -> None:
        """Uloží baseline výsledky od OBU."""
        session = self._get_session(session_id)
        # Merge s případným server-side baseline
        if session.baseline_data:
            session.baseline_data.update(baseline_data)
        else:
            session.baseline_data = baseline_data

    async def start_session(self, session_id: str) -> dict:
        """
        Spustí testovací session – aktivuje UC plugin a timeout monitor.

        Args:
            session_id: session k spuštění.

        Returns:
            dict: {status, start_timestamp_us}
        """
        session = self._get_session(session_id)
        if session.state not in ("INIT", "BASELINE"):
            raise ValueError(
                f"Cannot start session {session_id} in state {session.state}"
            )

        session.state = "RUNNING"
        session.start_time = time.monotonic()
        session.last_packet_time = time.monotonic()
        session.started_at = datetime.now(timezone.utc).isoformat()

        # Spusť UC plugin
        try:
            await session.plugin.start(
                params=session.effective_params,
                session_id=session_id,
                ports=session.ports,
                obu_ip=session.obu_ip,
            )
        except Exception as e:
            session.state = "ERROR"
            session.error_message = str(e)
            logger.error("Failed to start plugin for session %s: %s", session_id, e)
            raise

        # Spusť timeout monitor
        session.monitor_task = asyncio.create_task(
            self._monitor_timeout(session_id)
        )

        logger.info("Session started: %s", session_id)

        return {
            "status": "running",
            "start_timestamp_us": int(session.start_time * 1_000_000),
        }

    async def stop_session(
        self, session_id: str, obu_stats: Optional[dict] = None
    ) -> dict:
        """
        Zastaví session, evaluuje výsledky, uloží.

        Args:
            session_id: session k zastavení.
            obu_stats: statistiky od OBU (packets_sent, bytes_sent, ...).

        Returns:
            dict: kompletní výsledek testu.
        """
        session = self._get_session(session_id)

        # Cancel timeout monitor
        if session.monitor_task and not session.monitor_task.done():
            session.monitor_task.cancel()
            try:
                await session.monitor_task
            except asyncio.CancelledError:
                pass

        # Zastaví plugin a získá server-side stats
        server_stats = {}
        try:
            server_stats = await session.plugin.stop(session_id)
        except Exception as e:
            logger.error("Error stopping plugin for session %s: %s", session_id, e)
            server_stats = {"error": str(e)}

        if session.state == "RUNNING":
            session.state = "COMPLETED"

        # Evaluace
        profile = session.plugin.profile()
        measured = self._build_measured(server_stats, session)
        evaluation_result = session.plugin.evaluate(measured, obu_stats)

        # Sestav kompletní výsledek
        actual_duration = time.monotonic() - (session.start_time or time.monotonic())
        result = {
            "test_id": session_id,
            "uc_profile": session.uc_id,
            "uc_name": profile.name,
            "standard_reference": profile.standard_ref,
            "session_status": session.state,
            "interrupt_reason": session.interrupt_reason,
            "network_condition": session.network_condition,
            "lab_config": session.lab_config,
            "label": session.label,
            "started_at": session.started_at,
            "duration_s": session.duration_s,
            "duration_actual_s": round(actual_duration, 2),
            "obu_ip": session.obu_ip,
            "obu_app_version": session.obu_app_version,
            "effective_params": session.effective_params,
            "baseline": session.baseline_data,
            "measured": server_stats,
            "obu_reported_stats": obu_stats,
            "packet_delivery_ratio_pct": evaluation_result.get("packet_delivery_ratio_pct"),
            "normative_thresholds": dict(profile.thresholds),
            **evaluation_result,
        }

        # Uloží výsledek
        self._result_store.save(session_id, result)

        # Uvolni porty
        await self._port_allocator.release(session_id)

        logger.info(
            "Session %s completed: %s (pass=%s)",
            session_id, session.state, evaluation_result.get("overall_pass"),
        )

        return result

    def get_live_stats(self, session_id: str) -> dict:
        """Vrátí live statistiky pro SSE stream."""
        session = self._get_session(session_id)

        elapsed_s = 0.0
        if session.start_time:
            elapsed_s = time.monotonic() - session.start_time

        base = {
            "session_id": session_id,
            "state": session.state,
            "elapsed_s": round(elapsed_s, 1),
            "duration_s": session.duration_s,
        }

        if session.state == "RUNNING" and session.plugin:
            try:
                plugin_stats = session.plugin.get_live_stats(session_id)
                base.update(plugin_stats)
            except Exception as e:
                base["plugin_error"] = str(e)

        return base

    def update_last_packet_time(self, session_id: str) -> None:
        """Aktualizuje last_packet_time – voláno z transport vrstvy."""
        if session_id in self.sessions:
            self.sessions[session_id].last_packet_time = time.monotonic()

    async def _monitor_timeout(self, session_id: str) -> None:
        """
        Background task – sleduje aktivitu session.

        Pokud žádný paket přijat po NO_PACKET_TIMEOUT_S sekund:
        → session INTERRUPTED s důvodem no_packets_timeout.

        Pokud celková doba překročí SESSION_TIMEOUT_S:
        → session INTERRUPTED s důvodem session_timeout.
        """
        session = self.sessions.get(session_id)
        if not session:
            return

        try:
            while session.state == "RUNNING":
                await asyncio.sleep(1)

                if session.last_packet_time is None:
                    continue

                # Check no-packet timeout
                elapsed_since_packet = time.monotonic() - session.last_packet_time
                if elapsed_since_packet > NO_PACKET_TIMEOUT_S:
                    session.state = "INTERRUPTED"
                    session.interrupt_reason = "no_packets_timeout"
                    logger.warning(
                        "Session %s INTERRUPTED: no packets for %.1f s",
                        session_id, elapsed_since_packet,
                    )
                    await self._save_partial_results(session_id)
                    break

                # Check session timeout
                if session.start_time:
                    total_elapsed = time.monotonic() - session.start_time
                    if total_elapsed > SESSION_TIMEOUT_S:
                        session.state = "INTERRUPTED"
                        session.interrupt_reason = "session_timeout"
                        logger.warning(
                            "Session %s INTERRUPTED: total timeout %.0f s > %d s",
                            session_id, total_elapsed, SESSION_TIMEOUT_S,
                        )
                        await self._save_partial_results(session_id)
                        break

        except asyncio.CancelledError:
            pass

    async def _save_partial_results(self, session_id: str) -> None:
        """Uloží partial výsledky při INTERRUPTED session."""
        try:
            await self.stop_session(session_id)
        except Exception as e:
            logger.error("Failed to save partial results for %s: %s", session_id, e)

    def _build_measured(self, server_stats: dict, session: SessionState) -> dict:
        """
        Sestaví flat dict měřených hodnot pro evaluate().
        Mapuje server_stats klíče na názvy metrik používané v thresholds.
        """
        measured: dict[str, Any] = {}

        # UL metriky z BurstReceiver
        if "throughput_mbps" in server_stats:
            measured["ul_throughput_mbps"] = server_stats["throughput_mbps"]
        if "packets_received" in server_stats:
            measured["packets_received"] = server_stats["packets_received"]
        if "packet_loss_pct" in server_stats:
            # Reliability = 100 - loss
            measured["application_reliability_pct"] = 100 - server_stats["packet_loss_pct"]

        # DL metriky z UdpControlLoop / BurstSender
        if isinstance(server_stats.get("dl"), dict):
            dl = server_stats["dl"]
            if "avg_rtt_ms" in dl and dl["avg_rtt_ms"] is not None:
                measured["e2e_latency_ms"] = dl["avg_rtt_ms"] / 2  # RTT/2 aproximace
            if "throughput_mbps_actual" in dl:
                measured["dl_throughput_mbps"] = dl["throughput_mbps_actual"]
            if "packet_loss_pct" in dl:
                # Pro UC-C: DL reliability je kritická
                # Použijeme horší z UL a DL reliability
                dl_reliability = 100 - dl["packet_loss_pct"]
                if "application_reliability_pct" in measured:
                    measured["application_reliability_pct"] = min(
                        measured["application_reliability_pct"], dl_reliability
                    )
                else:
                    measured["application_reliability_pct"] = dl_reliability

        # Flat stats (pro UC s jednoduchým transport)
        if "avg_rtt_ms" in server_stats and server_stats["avg_rtt_ms"] is not None:
            measured["e2e_latency_ms"] = server_stats["avg_rtt_ms"] / 2

        return measured

    def _get_session(self, session_id: str) -> SessionState:
        """Vrátí session nebo raise ValueError."""
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found")
        return self.sessions[session_id]

    def get_session_state(self, session_id: str) -> Optional[str]:
        """Vrátí stav session nebo None."""
        session = self.sessions.get(session_id)
        return session.state if session else None
