"""
ITS-BO Test Platform – FastAPI Backend.

Main entry point. Zprovozňuje:
- Plugin loader (auto-discovery UC pluginů)
- Port allocator (dynamické porty per session)
- Session coordinator (lifecycle management)
- Result store (JSON soubory)
- 11 REST API endpoints
- CORS pro frontend
- SSE live feed pro real-time metriky

Spuštění:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import (
    API_PORT,
    CORS_ORIGINS,
    LOGS_DIR,
    RESULTS_DIR,
    SERVER_BIND_IP,
)
from core.plugin_loader import PluginLoader
from core.port_allocator import PortAllocator
from core.result_store import ResultStore
from core.session_coordinator import SessionCoordinator
from core.test_runner import TestRunner

# ──────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("itsbo.main")

# ──────────────────────────────────────────────────────────
# Global instances (initialized in lifespan)
# ──────────────────────────────────────────────────────────
plugin_loader: Optional[PluginLoader] = None
port_allocator: Optional[PortAllocator] = None
result_store: Optional[ResultStore] = None
coordinator: Optional[SessionCoordinator] = None
test_runner: Optional[TestRunner] = None
start_time: float = 0.0


# ──────────────────────────────────────────────────────────
# Lifespan – inicializace a cleanup
# ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializuje všechny komponenty při startu, cleanup při shutdown."""
    global plugin_loader, port_allocator, result_store, coordinator, test_runner, start_time

    start_time = time.monotonic()
    logger.info("═" * 60)
    logger.info("ITS-BO Test Platform starting...")
    logger.info("═" * 60)

    # Zajisti adresáře
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Inicializuj komponenty
    plugin_loader = PluginLoader()
    plugin_loader.load("plugins")

    port_allocator = PortAllocator()
    result_store = ResultStore()
    coordinator = SessionCoordinator(plugin_loader, port_allocator, result_store)
    test_runner = TestRunner(coordinator)

    status = plugin_loader.get_status()
    logger.info("Plugins loaded: %s", [p["uc_id"] for p in status["loaded"]])
    if status["errors"]:
        logger.warning("Plugin errors: %s", status["errors"])

    logger.info("ITS-BO Backend ready on %s:%d", SERVER_BIND_IP, API_PORT)
    logger.info("═" * 60)

    yield

    logger.info("ITS-BO Backend shutting down...")


# ──────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="ITS-BO Test Platform",
    description="C-ITS-S backoffice test platform for V2X communication testing",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────
# Pydantic models pro request validation
# ──────────────────────────────────────────────────────────
class SessionInitRequest(BaseModel):
    """POST /api/v1/session/init – OBU inicializuje session."""
    uc_id: str
    obu_ip: str
    label: str = ""
    network_condition: str = ""
    lab_config: Optional[dict] = None
    params: dict = Field(default_factory=dict)
    requested_duration_s: Optional[int] = None
    obu_app_version: str = ""


class SessionStartRequest(BaseModel):
    """POST /api/v1/session/start – OBU spustí test."""
    session_id: str


class SessionStopRequest(BaseModel):
    """POST /api/v1/session/stop – OBU ukončí test, vrátí výsledky."""
    session_id: str
    obu_stats: Optional[dict] = None


class BaselineStartRequest(BaseModel):
    """POST /api/v1/baseline/start – připraví ITS-BO pro baseline."""
    session_id: str
    obu_ip: str


class BaselineResultRequest(BaseModel):
    """POST /api/v1/baseline/result – OBU nahraje baseline data."""
    session_id: str
    baseline_data: dict


# ──────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────

@app.get("/api/v1/profiles")
async def get_profiles():
    """
    Dynamický seznam UC profilů z plugin loaderu.
    OBU/Frontend volá při startu pro zobrazení dostupných UC.
    """
    return plugin_loader.get_profiles()


@app.get("/api/v1/system/status")
async def get_system_status():
    """
    Stav systému: nabité pluginy, volné porty, uptime.
    Používá se pro health check a pre-flight z OBU.
    """
    uptime_s = time.monotonic() - start_time
    return {
        "status": "online",
        "uptime_s": round(uptime_s, 1),
        "uptime_human": f"{int(uptime_s // 3600)}h {int((uptime_s % 3600) // 60)}m",
        "plugins": plugin_loader.get_status(),
        "ports": {
            "free_burst": port_allocator.free_burst_count,
            "free_control": port_allocator.free_control_count,
            "active_sessions": port_allocator.active_sessions,
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/session/init")
async def init_session(req: SessionInitRequest):
    """
    OBU inicializuje testovací session.

    Backend:
    1. Vygeneruje session_id
    2. Alokuje porty (PortAllocator)
    3. Připraví transport vrstvu
    4. Provede pre-flight check
    5. Vrátí effective_params
    """
    try:
        result = await coordinator.init_session(
            uc_id=req.uc_id,
            obu_ip=req.obu_ip,
            label=req.label,
            network_condition=req.network_condition,
            lab_config=req.lab_config,
            params=req.params,
            requested_duration_s=req.requested_duration_s,
            obu_app_version=req.obu_app_version,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/v1/session/start")
async def start_session(req: SessionStartRequest):
    """
    OBU spustí test. Obě strany startují datový přenos od tohoto okamžiku.
    """
    try:
        result = await coordinator.start_session(req.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/session/stop")
async def stop_session(req: SessionStopRequest):
    """
    OBU ukončí test.

    OBU posílá obu_stats (packets_sent, bytes_sent, ...) pro výpočet
    packet_delivery_ratio. Backend zastaví pluginy, evaluuje výsledky,
    uloží a vrátí kompletní result.
    """
    try:
        result = await coordinator.stop_session(req.session_id, req.obu_stats)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error stopping session %s: %s", req.session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/session/status/{session_id}")
async def session_status_sse(session_id: str, request: Request):
    """
    SSE stream live metrik (1s interval).

    Frontend se připojí přes EventSource a dostává JSON events
    s aktuálními statistikami (throughput, RTT, loss, ...).
    """
    state = coordinator.get_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    async def event_generator():
        async for event in test_runner.live_stats_stream(session_id):
            if await request.is_disconnected():
                break
            yield event

    return EventSourceResponse(event_generator())


@app.post("/api/v1/baseline/start")
async def start_baseline(req: BaselineStartRequest):
    """
    Připraví ITS-BO pro baseline příjem.
    Spustí ping baseline a vrátí výsledky.
    """
    try:
        result = await coordinator.start_baseline(req.session_id, req.obu_ip)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/baseline/result")
async def store_baseline_result(req: BaselineResultRequest):
    """OBU nahraje baseline výsledky."""
    try:
        await coordinator.store_baseline_result(req.session_id, req.baseline_data)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/results/{session_id}")
async def get_result(session_id: str):
    """Kompletní JSON výsledek jednoho testu."""
    result = result_store.get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result '{session_id}' not found")
    return result


@app.get("/api/v1/results/history")
async def get_results_history(limit: int = 100):
    """Seznam všech výsledků seřazený desc (newest first)."""
    return result_store.list_results(limit=limit)


# ──────────────────────────────────────────────────────────
# Health check (non-API)
# ──────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Jednoduchý health check."""
    return {"status": "ok"}
