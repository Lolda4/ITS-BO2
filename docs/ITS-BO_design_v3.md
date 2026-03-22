# ITS-BO Test Platform – Implementační specifikace v3

> Verze: 3.0 | Datum: 2026-03-22
> Kontext: Diplomová práce ČVUT – Metodický rámec pro testování datově náročných ITS aplikací v sítích 4G/5G
> Vedoucí: Ing. Martin Šrotýř, Ph.D.
> Poznámka: Tento dokument je kompletní implementační specifikace. Postav podle něj celý backend, transport vrstvu a frontend. Každý soubor, každá funkce, každý datový typ je zde popsán. IP adresy jsou placeholder – budou doplněny.

---

## 1. Identita a účel

### 1.1 Co to je

ITS-BO Test Platform je softwarová simulace **C-ITS-S (Central ITS Station)** – backoffice uzlu V2X komunikační infrastruktury dle ETSI EN 302 665. Slouží jako normativně ukotvená protistrana pro mobilní zařízení (V-ITS-S / OBU) připojené přes mobilní síť.

Platforma je **aktivním obousměrným účastníkem** komunikace – simuluje aplikační komunikační vzor každého UC včetně DL provozu, struktury zpráv odpovídající ETSI datovým slovníkům a reaktivního chování. Není to pasivní příjemce ani prostý síťový benchmark.

### 1.2 Normativní ukotvení

| Standard | Verze | Relevance |
|---|---|---|
| ETSI EN 302 665 | V1.1.1 | ITS Communications Architecture – definice C-ITS-S |
| 3GPP TS 22.186 | v18.0.1 | Service requirements for enhanced V2X – normativní prahy UC |
| ETSI TS 103 324 | v2.1.1 | Collective Perception Service – struktura CPM zpráv |
| ETSI TR 103 562 | v2.1.1 | Analýza CPS – informativní ASN.1, CPM messageId = 14 |
| ETSI TS 102 894-2 | V1.3.1 | Common Data Dictionary – datové elementy zpráv |
| ISO 24089 | 2023 | OTA Software Update – UC-D referenční standard |
| RFC 5357 (TWAMP) | — | Metodologie měření latence a packet loss |

### 1.3 Vymezení implementace

Platforma implementuje vybrané aspekty standardů. Toto vymezení je proaktivně dokumentováno:

| Aspekt | Implementováno | Poznámka |
|---|---|---|
| Datová struktura zpráv | ✅ JSON | Sémanticky věrné dle TS 103 324, TS 102 894-2 |
| Frekvence a timing | ✅ | Normativní hodnoty per standard |
| Payload velikost | ✅ | Per UC normativní reference, paddovány na cílovou velikost |
| Obousměrná komunikace | ✅ | Plně implementováno pro UC-A, UC-B, UC-C |
| ASN.1 UPER kódování | ❌ JSON | Ekvivalentní datový obsah, jiná serializace – viz odůvodnění níže |
| GeoNetworking / BTP | ❌ UDP/IP | Uu interface nepodporuje GN stack |
| PKI / certifikáty | ❌ | Mimo scope – testujeme síťový výkon, ne bezpečnost |
| DCC (ITS-G5 specific) | ❌ | Specifické pro ITS-G5, neaplikovatelné na Uu |

**Obhajitelný argument JSON vs. ASN.1:** Přenos přes Uu interface (C-V2X) je normativně definovaný komunikační profil dle 3GPP. 3GPP nepředepisuje konkrétní serializaci na aplikační vrstvě Uu, pouze datové požadavky (velikost, frekvence, latence). JSON payloady jsou paddovány na normativní velikost (např. 1600 B dle R.5.4-001), čímž je rozdíl v serializační eficienci eliminován. Framework hodnotí schopnosti sítě přenést V2X datový profil – nikoliv certifikuje ETSI ITS stack.

### 1.4 PASS/FAIL jako vědecký výsledek

PASS/FAIL verdikt má vědeckou hodnotu. FAIL neindikuje selhání systému – prokazuje nedostatečnost sítě pro daný UC. Například UC-C vyžaduje RTT ≤ 5 ms, LTE/NR NSA dosahuje typicky 8–20 ms. Kvantifikace této mezery je primárním hodnotovým přínosem frameworku.

### 1.5 Měření reliability – vrstva měření

3GPP TS 22.186 definuje reliability na L2/L3 rádio vrstvě. Framework měří reliability na **aplikační vrstvě** (end-to-end packet delivery ratio). Aplikační reliability je přísnějším měřítkem – zahrnuje ztráty v rádio vrstvě, OS stacku, transportním protokolu i serverovém zpracování. V výsledcích je jasně označena jako `application_reliability_pct` s poznámkou, že normativní definice se vztahuje k rádio vrstvě.

### 1.6 Měření latence – RTT metodologie

**Kritické rozhodnutí:** OBU a ITS-BO **nemají** NTP/PTP synchronizaci. Veškerá latence je proto měřena jako **round-trip time (RTT)** na straně ITS-BO:

```
RTT = ack_receive_timestamp_us − mcm_send_timestamp_us
```

Obě timestamps jsou z jednoho hostu (ITS-BO), tedy ze stejných hodin – není třeba clock synchronizace. E2E latence je aproximována jako RTT/2. V diplomce je asymetrie UL/DL uvedena jako omezení této aproximace.

OBU strana měří pouze **lokální processing delay** (čas od přijetí MCM do odeslání ACK), nikoliv RTT.

---

## 2. Deployment prostředí

### 2.1 Dva deployment režimy

#### Lab deployment (Amarisoft Callbox)

```
[OnePlus 8 Pro / OBU App]
  <UE_IP> (UE IP od EPC, typicky 192.168.3.x)
       │
       │ LTE/5G Uu interface (air)
       │
[Amarisoft Callbox CBC-2019103002]
  eNodeB/gNB + EPC (mme-ims.cfg)
  IP: <CALLBOX_IP>
  tun1: gateway pro UE subnet
       │
       │ Ethernet (LAN)
       │
[ITS-BO VM – Ubuntu 24.04]
  IP: <ITS_BO_LAB_IP>
  Static route: <UE_SUBNET>/24 via <CALLBOX_IP>
  Frontend :3000 | Backend :8000
```

| Parametr | Hodnota |
|---|---|
| Host OS | Ubuntu 24.04 LTS |
| Platforma | VMware Workstation 17 Player (Bridged network) NEBO nativní Linux |
| RAM | 4 GB |
| CPU | 2 vCPU |
| Disk | 20 GB |
| Frontend port | 3000 |
| Backend port | 8000 |
| BurstReceiver UL port range | 5100–5199 (dynamicky přidělováno per session) |
| UDP Control Loop port range | 4500–4599 (dynamicky přidělováno per session) |
| Baseline receiver port | 5200 |

#### Field deployment (komerční operátoři)

```
[OnePlus 8 Pro / OBU App]
  mobilní IP (T-Mobile/O2/Vodafone CZ)
       │
       │ Komerční 4G/5G síť
       │
       │ Internet
       │
[VPS Server – Praha/Frankfurt]
  Veřejná IP: <VPS_PUBLIC_IP>
  ITS-BO Backend :8000
  ITS-BO Frontend :3000
  UDP porty: 4500-5200 otevřené ve firewallu
```

Pro terénní testování se ITS-BO backend nasadí na VPS s veřejnou IP adresou. OBU app se připojí přes hostname nebo IP adresu VPS. Instalace na VPS je identická s lab instalací (stejný `install.sh`), bez statické route (VPS má veřejnou IP, OBU má mobilní IP – komunikace jde přes internet).

**Firewall na VPS:** Otevřít TCP 8000 (API), TCP 3000 (frontend), UDP 4500-5200 (transport).

### 2.2 Latence – realistická očekávání

| Konfigurace | Typický ping RTT | Poznámka |
|---|---|---|
| Lab – LTE (μ=0, 1ms TTI) | 8–20 ms | 2× TTI + Linux tun overhead + EPC |
| Lab – NR NSA (μ=1) | 5–12 ms | NR radio, data plane stále přes LTE EPC |
| Lab – NR SA (pokud dostupné) | 3–8 ms | Kratší cesta, Linux overhead zůstává |
| Field – komerční 4G | 20–60 ms | Závisí na operátoru a zatížení |
| Field – komerční 5G NSA | 10–30 ms | Závisí na operátoru |

Sub-5ms RTT (UC-C požadavek) není s NSA konfigurací dosažitelné. Toto je záměrný výsledek dokumentující mezeru.

VMware Workstation Player přidává overhead ~0.1–0.5 ms (steady state), se spiky až 5–10 ms. Pro UC-C se doporučuje nativní Linux boot pro nejpřesnější výsledky.

---

## 3. Architektura systému

### 3.1 Čtyřvrstvá architektura

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND – Next.js 14 (port 3000)                             │
│  React + Tailwind CSS + SSE klient + Session control UI        │
├─────────────────────────────────────────────────────────────────┤
│  BACKEND – Python FastAPI (port 8000)                          │
│  Plugin loader │ Session coordinator │ REST + SSE server       │
├─────────────────────────────────────────────────────────────────┤
│  UC PLUGIN LAYER                                               │
│  uc_a_sdsm │ uc_b_see_through │ uc_c_teleop │ uc_d_ota        │
│  Každý plugin = samostatný soubor, auto-načítán               │
├─────────────────────────────────────────────────────────────────┤
│  TRANSPORT LAYER                                               │
│  BurstReceiver │ BurstSender │ AppLayerSimulator               │
│  UdpControlLoop │ BaselineRunner │ PortAllocator               │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Backend adresářová struktura

```
its-bo-backend/
├── main.py                          # FastAPI app, CORS, lifespan startup
├── config.py                        # Centrální konfigurace (env vars + defaults)
├── requirements.txt
├── install.sh                       # Instalační skript (sysctl, pip, npm, systemd)
├── core/
│   ├── __init__.py
│   ├── base_uc.py                   # Abstraktní třída BaseUseCase + UCProfile dataclass
│   ├── plugin_loader.py             # Auto-discovery UC pluginů z plugins/
│   ├── session_coordinator.py       # Handshake, session lifecycle, port allocation
│   ├── test_runner.py               # Orchestrace transportů, SSE live feed, timeout
│   ├── result_store.py              # Ukládání JSON výsledků do results/
│   ├── preflight.py                 # Pre-flight validace před každým testem
│   └── port_allocator.py            # Dynamická alokace portů per session
├── plugins/
│   ├── __init__.py
│   ├── uc_a_sdsm.py                 # UC-A: Extended Sensors / CPM
│   ├── uc_b_see_through.py          # UC-B: See-Through / Video
│   ├── uc_c_teleop.py               # UC-C: Tele-Operated Driving
│   └── uc_d_ota.py                  # UC-D: OTA Software Update
├── transports/
│   ├── __init__.py
│   ├── burst_receiver.py            # UDP/TCP příjem s per-packet metrikami
│   ├── burst_sender.py              # UDP/TCP odesílání dle UC profilu
│   ├── app_layer_simulator.py       # UC-specifické payload generátory
│   ├── udp_control_loop.py          # Bidirectionální UDP, RTT měření, MCM/ACK
│   └── baseline_runner.py           # Referenční baseline měření (ICMP ping + burst)
├── results/                         # JSON výsledky testů (auto-vytvořeno)
└── logs/                            # Debug logy per session
```

### 3.3 config.py – centrální konfigurace

```python
"""
Centrální konfigurace. Hodnoty se berou z env vars, s rozumnými defaults.
Při terénním nasazení na VPS se změní jen SERVER_BIND_IP.
"""
import os

# Síťová konfigurace
SERVER_BIND_IP = os.getenv("ITSBO_BIND_IP", "0.0.0.0")
API_PORT = int(os.getenv("ITSBO_API_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("ITSBO_FRONTEND_PORT", "3000"))

# Dynamické porty – rozsahy pro per-session alokaci
BURST_PORT_RANGE_START = int(os.getenv("ITSBO_BURST_PORT_START", "5100"))
BURST_PORT_RANGE_END = int(os.getenv("ITSBO_BURST_PORT_END", "5199"))
CONTROL_PORT_RANGE_START = int(os.getenv("ITSBO_CONTROL_PORT_START", "4500"))
CONTROL_PORT_RANGE_END = int(os.getenv("ITSBO_CONTROL_PORT_END", "4599"))
BASELINE_PORT = int(os.getenv("ITSBO_BASELINE_PORT", "5200"))

# UDP buffer – KRITICKÉ pro příjem 25 Mbps bez ztrát
UDP_RECV_BUFFER_BYTES = int(os.getenv("ITSBO_UDP_RECV_BUF", "4194304"))  # 4 MB

# Test defaults
DEFAULT_TEST_DURATION_S = int(os.getenv("ITSBO_DEFAULT_DURATION", "60"))
SESSION_TIMEOUT_S = int(os.getenv("ITSBO_SESSION_TIMEOUT", "300"))
NO_PACKET_TIMEOUT_S = int(os.getenv("ITSBO_NO_PACKET_TIMEOUT", "10"))

# Cesty
RESULTS_DIR = os.getenv("ITSBO_RESULTS_DIR", "results")
LOGS_DIR = os.getenv("ITSBO_LOGS_DIR", "logs")

# CORS
CORS_ORIGINS = ["*"]  # Lab prostředí, žádná autentizace
```

---

## 4. Koordinační protokol (Session Handshake)

Test je vždy **iniciován z OBU app** (mobilu). ITS-BO čeká na příchozí session request.

### 4.1 Kompletní handshake sekvence

```
OBU App                              ITS-BO Backend
    │                                     │
    │── POST /api/v1/session/init ────────►│
    │   {uc_id, params, label,            │
    │    network_condition, obu_ip,       │
    │    obu_app_version,                 │
    │    requested_duration_s}            │
    │                                     │  Backend:
    │                                     │  1. Vygeneruje session_id
    │                                     │  2. Alokuje porty (PortAllocator)
    │                                     │  3. Připraví transport vrstvu
    │                                     │  4. Provede pre-flight check
    │                                     │  5. Vrátí effective_params
    │                                     │
    │◄── {session_id, server_ready,       │
    │     allocated_ports: {              │
    │       burst_port, control_port},    │
    │     effective_params: {...},         │
    │     start_timestamp_us,             │
    │     duration_s,                     │
    │     preflight_warnings: [...]}  ────│
    │                                     │
    │── POST /api/v1/baseline/start ─────►│  (volitelné)
    │   {session_id, obu_ip}             │
    │                                     │  Spustí baseline receiver
    │◄── {baseline_ready: true} ─────────│
    │                                     │
    │   [OBU provede baseline]            │
    │                                     │
    │── POST /api/v1/baseline/result ────►│  (volitelné)
    │   {session_id, baseline_data}      │
    │◄── {ok} ───────────────────────────│
    │                                     │
    │   [OBU zobrazí 3-2-1 countdown]    │
    │                                     │
    │── POST /api/v1/session/start ──────►│
    │   {session_id}                     │
    │                                     │  Obě strany startují
    │◄════════ datový přenos UC ═════════►│  od tohoto okamžiku
    │                                     │
    │                                     │  [Timeout detekce:
    │                                     │   pokud žádný paket >10s
    │                                     │   → session INTERRUPTED]
    │                                     │
    │── POST /api/v1/session/stop ───────►│
    │   {session_id,                     │
    │    obu_stats: {packets_sent, ...}} │
    │                                     │
    │◄── {session_id, server_stats,      │
    │     evaluation, overall_pass,      │
    │     packet_delivery_ratio,         │
    │     interpretation} ───────────────│
```

### 4.2 session_id

Formát: `{uc_id}-{YYYYMMDD}-{HHMMSS}-{random4}` generovaný serverem. Random suffix zabraňuje kolizi při rychlém spuštění více testů. Toto je zároveň `test_id` v obou výsledcích (OBU i ITS-BO).

### 4.3 Dynamická alokace portů

```python
class PortAllocator:
    """
    Přiděluje volné porty z definovaných rozsahů per session.
    Při ukončení session se porty vrátí do poolu.
    Řeší problém: souběžné sessions by jinak kolidovaly na pevných portech.
    """
    def __init__(self):
        self._burst_pool = set(range(BURST_PORT_RANGE_START, BURST_PORT_RANGE_END + 1))
        self._control_pool = set(range(CONTROL_PORT_RANGE_START, CONTROL_PORT_RANGE_END + 1))
        self._allocated = {}  # session_id → {burst_port, control_port}
        self._lock = asyncio.Lock()

    async def allocate(self, session_id: str) -> dict:
        """Vrátí {burst_port: int, control_port: int} nebo raise pokud vyčerpáno."""
        async with self._lock:
            if not self._burst_pool or not self._control_pool:
                raise RuntimeError("No free ports available")
            bp = self._burst_pool.pop()
            cp = self._control_pool.pop()
            self._allocated[session_id] = {"burst_port": bp, "control_port": cp}
            return {"burst_port": bp, "control_port": cp}

    async def release(self, session_id: str):
        """Vrátí porty do poolu."""
        async with self._lock:
            if session_id in self._allocated:
                ports = self._allocated.pop(session_id)
                self._burst_pool.add(ports["burst_port"])
                self._control_pool.add(ports["control_port"])
```

### 4.4 Pre-flight check

```python
class PreflightChecker:
    """
    Před každým testem ověří readiness.
    Výsledek je součástí session/init response jako preflight_warnings.
    Varování neblokují test – tester rozhoduje.
    """
    async def check(self, obu_ip: str, ports: dict) -> list[dict]:
        warnings = []
        # 1. Ping OBU IP (max 1s timeout)
        if not await self._ping(obu_ip, timeout_s=1):
            warnings.append({"level": "warning", "msg": f"OBU IP {obu_ip} neodpovídá na ping"})
        # 2. Alokované porty volné
        for name, port in ports.items():
            if not self._port_free(port):
                warnings.append({"level": "error", "msg": f"Port {port} ({name}) je obsazený"})
        # 3. Results directory zapisovatelný
        if not os.access(RESULTS_DIR, os.W_OK):
            warnings.append({"level": "error", "msg": "Results directory není zapisovatelný"})
        # 4. Disk space > 100 MB
        free_mb = shutil.disk_usage(RESULTS_DIR).free / 1024 / 1024
        if free_mb < 100:
            warnings.append({"level": "warning", "msg": f"Málo místa na disku: {free_mb:.0f} MB"})
        return warnings
```

### 4.5 Session lifecycle a timeout

```python
class SessionCoordinator:
    """
    Spravuje životní cyklus sessions.
    States: INIT → BASELINE → READY → RUNNING → COMPLETED | INTERRUPTED | ERROR
    """
    # INTERRUPTED = žádný paket přijat po NO_PACKET_TIMEOUT_S sekund
    # ERROR = výjimka v transportní vrstvě
    # Timeout: session je automaticky ukončena po SESSION_TIMEOUT_S od init

    async def monitor_timeout(self, session_id: str):
        """Background task – sleduje aktivitu session."""
        last_packet_time = time.monotonic()
        while self.sessions[session_id].state == "RUNNING":
            await asyncio.sleep(1)
            if self.sessions[session_id].last_packet_time:
                last_packet_time = self.sessions[session_id].last_packet_time
            elapsed_since_packet = time.monotonic() - last_packet_time
            if elapsed_since_packet > NO_PACKET_TIMEOUT_S:
                self.sessions[session_id].state = "INTERRUPTED"
                self.sessions[session_id].interrupt_reason = "no_packets_timeout"
                await self._save_partial_results(session_id)
                break
```

---

## 5. Modulární UC Plugin Systém

### 5.1 Princip

Každý UC je samostatný soubor v `plugins/`. Plugin loader při startu automaticky prohledá složku a načte všechny třídy dědící `BaseUseCase`. Přidat nový UC = vytvořit jeden soubor v `plugins/`. Odebrat = smazat soubor.

Plugin loader zachytává výjimky per-plugin při registraci. Chybný plugin = disabled s chybovou zprávou v `/api/v1/system/status`. Ostatní UC fungují dál.

### 5.2 UCProfile dataclass

```python
@dataclass(frozen=True)  # frozen = immutable
class UCProfile:
    id: str                        # "UC-A"
    name: str                      # "Extended Sensors / SDSM"
    standard_ref: str              # "3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-004]"
    description: str
    communication_pattern: str     # "UL_ONLY" | "DL_ONLY" | "BIDIRECTIONAL" | "BIDIRECTIONAL_ASYMMETRIC"
    ul_transport: str              # "burst_udp" | "app_cpm" | "app_video" | "none"
    dl_transport: str              # "app_control" | "app_video" | "app_ota" | "burst_udp" | "app_cpm_aggregated" | "none"
    thresholds: dict               # {metric: {value, op, ref}} – IMMUTABLE
    default_params: dict           # {packet_size, interval_ms, bitrate_mbps, ...}
    baseline_required: bool        # True = spustit baseline před testem
    min_repetitions: int           # Doporučený minimální počet opakování (lab: 3, field: 5)
    default_duration_s: int        # Výchozí délka testu v sekundách
```

### 5.3 BaseUseCase abstraktní třída

```python
class BaseUseCase(ABC):
    """
    Každý plugin MUSÍ implementovat tyto metody.
    evaluate() má defaultní implementaci – porovnává measured vs. thresholds.
    """
    @abstractmethod
    def profile(self) -> UCProfile: ...

    @abstractmethod
    async def start(self, params: dict, session_id: str, ports: dict, obu_ip: str): ...

    @abstractmethod
    async def stop(self, session_id: str) -> dict: ...

    @abstractmethod
    async def get_live_stats(self, session_id: str) -> dict: ...

    def evaluate(self, measured: dict, obu_stats: dict = None) -> dict:
        """
        Defaultní evaluace: pro každý threshold porovná measured hodnotu.
        obu_stats: pokud OBU poslal stats v session/stop, použijí se pro packet_delivery_ratio.
        Vrací: {metric: {measured, threshold, op, pass, ref}, ..., overall_pass, interpretation}
        """
        profile = self.profile()
        evaluation = {}
        all_pass = True
        for metric, thresh in profile.thresholds.items():
            val = measured.get(metric)
            if val is None:
                evaluation[metric] = {"measured": None, "threshold": thresh["value"],
                                      "op": thresh["op"], "pass": False, "ref": thresh["ref"],
                                      "note": "metric not measured"}
                all_pass = False
                continue
            if thresh["op"] == "<=":
                passed = val <= thresh["value"]
            elif thresh["op"] == ">=":
                passed = val >= thresh["value"]
            else:
                passed = val == thresh["value"]
            evaluation[metric] = {"measured": val, "threshold": thresh["value"],
                                  "op": thresh["op"], "pass": passed, "ref": thresh["ref"]}
            if not passed:
                all_pass = False

        # Packet delivery ratio (OBU sent vs. ITS-BO received)
        pdr = None
        if obu_stats and "packets_sent" in obu_stats and "packets_received" in measured:
            sent = obu_stats["packets_sent"]
            if sent > 0:
                pdr = measured["packets_received"] / sent * 100

        interpretation = self._generate_interpretation(evaluation, all_pass, measured)
        return {
            "evaluation": evaluation,
            "overall_pass": all_pass,
            "packet_delivery_ratio_pct": pdr,
            "interpretation": interpretation
        }

    def _generate_interpretation(self, evaluation, all_pass, measured) -> str:
        """Generuje srozumitelný textový závěr pro diplomku."""
        profile = self.profile()
        if all_pass:
            return f"PASS – Síť splňuje všechny požadavky {profile.id} ({profile.name}) dle {profile.standard_ref}."
        fails = [f"{m}: naměřeno {e['measured']}, požadavek {e['op']} {e['threshold']} [{e['ref']}]"
                 for m, e in evaluation.items() if not e["pass"]]
        return (f"FAIL – Síť nesplňuje {profile.id} požadavky. "
                f"Nesplněné metriky: {'; '.join(fails)}.")

    @abstractmethod
    def get_obu_instructions(self, params: dict) -> str: ...
```

---

## 6. UC Profily – Normativní parametry

### UC-A: Extended Sensors / SDSM

**POZOR – oprava z v2:** Původně byl uveden R.5.4-003 (E2E latence 3 ms, 50 Mbps, 99.999%). Tento řádek je extrémně náročný a pro účely frameworku používáme **R.5.4-004** (10 ms, 25 Mbps, 99.99%, 500 m). Zdůvodnění: R.5.4-003 vyžaduje 3 ms E2E latenci, která je mimo dosah nejen testovací infrastruktury ale i současných komerčních sítí. R.5.4-004 je realistický benchmark pro Higher degree of automation CPS. Payload size a Tx rate pocházejí z R.5.4-001 (1600 B, 10 msg/s) – tyto hodnoty jsou sdíleny všemi řádky.

| Parametr | Hodnota | Normativní reference |
|---|---|---|
| Standard | 3GPP TS 22.186 v18.0.1 Table 5.4-1 | |
| Max E2E latence | ≤ 10 ms | R.5.4-004 |
| Spolehlivost (app-level) | ≥ 99,99 % | R.5.4-004 |
| UL throughput | ≥ 25 Mbps | R.5.4-004 (peak) |
| UL payload size | 1600 B | R.5.4-001 |
| UL Tx rate | 10 msg/s | R.5.4-001 |
| Min range | 500 m | R.5.4-004 |
| Protokol | UDP | |
| Communication pattern | BIDIRECTIONAL | |
| UL transport | app_cpm | |
| DL transport | app_cpm_aggregated | |
| default_duration_s | 60 | |
| min_repetitions | 3 (lab) / 5 (field) | |

**Komunikační vzor:**
OBU → ITS-BO: CPM-like zprávy 1600 B @ 10 Hz (na alokovaný control_port, UDP)
ITS-BO → OBU: agregovaná situační mapa (sloučené objekty)

**ITS-BO DL chování – AppLayerSimulator (UC-A):**
Server udržuje buffer přijatých objektů z posledních 500 ms. Každých 100 ms (10 Hz) odešle zpět aktualizovanou mapu obsahující sloučení objektů ze všech přijatých CPM – věrná simulace ITS-BO agregační funkce dle TS 103 324 §6.1. Velikost DL zprávy roste s počtem objektů (minimum 1 objekt, maximum 20 pro testovací účely).

**Plugin implementace (uc_a_sdsm.py):**

```python
class UcASdsm(BaseUseCase):
    def profile(self) -> UCProfile:
        return UCProfile(
            id="UC-A",
            name="Extended Sensors / SDSM",
            standard_ref="3GPP TS 22.186 v18.0.1 Table 5.4-1 [R.5.4-004]",
            description="Collective Perception – sdílení senzorových dat mezi vozidly/infrastrukturou",
            communication_pattern="BIDIRECTIONAL",
            ul_transport="app_cpm",
            dl_transport="app_cpm_aggregated",
            thresholds={
                "e2e_latency_ms": {"value": 10, "op": "<=", "ref": "R.5.4-004"},
                "application_reliability_pct": {"value": 99.99, "op": ">=", "ref": "R.5.4-004"},
                "ul_throughput_mbps": {"value": 25, "op": ">=", "ref": "R.5.4-004"},
            },
            default_params={
                "payload_size_bytes": 1600,
                "tx_rate_hz": 10,
                "num_objects_per_cpm": 5,
                "aggregation_window_ms": 500,
            },
            baseline_required=True,
            min_repetitions=3,
            default_duration_s=60,
        )

    async def start(self, params, session_id, ports, obu_ip):
        """
        1. Spustí BurstReceiver na ports["burst_port"] pro příjem CPM z OBU
        2. Spustí AppLayerSimulator pro DL – agregační mapa zpět na OBU
        3. Obě větve jako asyncio tasks
        """
        effective = {**self.profile().default_params, **params}
        # UL: BurstReceiver pro CPM příjem
        self._ul_receiver = BurstReceiver()
        await self._ul_receiver.start(
            port=ports["burst_port"],
            protocol="udp",
            session_id=session_id,
            recv_buffer_bytes=UDP_RECV_BUFFER_BYTES
        )
        # DL: AppLayerSimulator – agregovaná mapa
        self._dl_sender = AppLayerSimulator()
        self._dl_task = asyncio.create_task(
            self._dl_sender.run_cpm_aggregation(
                target_ip=obu_ip,
                target_port=ports["control_port"],
                session_id=session_id,
                ul_receiver=self._ul_receiver,
                aggregation_window_ms=effective["aggregation_window_ms"],
                tx_rate_hz=effective["tx_rate_hz"],
            )
        )

    async def stop(self, session_id):
        self._dl_task.cancel()
        await self._ul_receiver.stop(session_id)
        return self._ul_receiver.get_stats(session_id)
```

---

### UC-B: See-Through (Video Sharing)

**Oprava z v2:** Používáme výhradně R.5.4-009 jako kompletní set požadavků (Higher degree of automation, range 400 m). Nekomibujeme s R.5.4-008.

| Parametr | Hodnota | Normativní reference |
|---|---|---|
| Standard | 3GPP TS 22.186 v18.0.1 Table 5.4-1 | |
| Max E2E latence | ≤ 10 ms | R.5.4-009 (sloupec Tx rate v tabulce) |
| Spolehlivost (app-level) | ≥ 99,99 % | R.5.4-009 |
| Throughput (UL i DL) | ≥ 10 Mbps | R.5.4-009 (sloupec Data rate) |
| Min range | 400 m | R.5.4-009 |
| Protokol | UDP | |
| Communication pattern | BIDIRECTIONAL | |
| UL transport | app_video | |
| DL transport | app_video | |
| default_duration_s | 60 | |
| min_repetitions | 3 (lab) / 5 (field) | |

**Komunikační vzor:**
OBU → ITS-BO: video-like UL burst (I-frame ~50 KB každých 30 paketů, P-frame ~5 KB – simuluje H.264 GOP strukturu)
ITS-BO → OBU: symetrický video DL burst (stejný pattern) – simuluje infrastrukturní kameru

**ITS-BO DL chování – AppLayerSimulator (UC-B):**
DL video burst běží nezávisle na UL příjmu. Generátor produkuje GOP pattern: 1× I-frame (~50 KB, rozložen do ~34 paketů po 1472 B), poté 29× P-frame (~5 KB, 3–4 pakety). Cyklus 30 framů @ 30 fps = 1 sekunda. Bitrate řízení: inter-frame interval = (frame_size × 8) / target_bitrate_bps, s adaptivní kompenzací skutečného elapsed.

---

### UC-C: Tele-Operated Driving

| Parametr | Hodnota | Normativní reference |
|---|---|---|
| Standard | 3GPP TS 22.186 v18.0.1 Table 5.5-1 | |
| Max E2E latence (řídicí smyčka) | ≤ 5 ms | R.5.5-002 |
| Spolehlivost (app-level) | ≥ 99,999 % | R.5.5-002 |
| UL throughput (video + telemetrie) | ≥ 25 Mbps | R.5.5-002 |
| DL throughput (řídicí příkazy) | ≥ 1 Mbps | R.5.5-002 |
| DL packet size | 256 B | Odhad autora dle typického MCM řídicího obsahu (§5.5) |
| DL interval (řídicí smyčka) | 100 ms (10 Hz) | Odvozeno z typické řídicí frekvence |
| Protokol UL | UDP (burst) | |
| Protokol DL | UDP (control loop) | |
| Communication pattern | BIDIRECTIONAL_ASYMMETRIC | |
| default_duration_s | 60 | |
| min_repetitions | 3 (lab) / 5 (field) | |

**Komunikační vzor – dvě paralelní nezávislé větve:**

**UL větev** (video + telemetrie): OBU → ITS-BO: BurstEngine UDP @ 25 Mbps. ITS-BO: BurstReceiver přijímá, měří throughput, jitter, loss.

**DL větev** (řídicí smyčka – KRITICKÁ): ITS-BO → OBU: UdpControlLoop posílá MCM zprávy @ 10 Hz. OBU → ITS-BO: ACK na každý příkaz okamžitě. **RTT měřeno na ITS-BO:** `ack_receive_time_us - mcm_send_time_us` (obě timestamps z jednoho hostu = nepotřebuje clock sync). **Delta RTT** je kritická metrika.

**Plugin implementace (uc_c_teleop.py):**

```python
class UcCTeleOp(BaseUseCase):
    async def start(self, params, session_id, ports, obu_ip):
        """
        Spustí DVĚ paralelní větve jako nezávislé asyncio tasks:
        1. UL: BurstReceiver na ports["burst_port"] pro 25 Mbps video stream z OBU
        2. DL: UdpControlLoop na ports["control_port"] – MCM @ 10 Hz s RTT měřením
        """
        effective = {**self.profile().default_params, **params}

        # UL větev – video příjem
        self._ul_receiver = BurstReceiver()
        await self._ul_receiver.start(
            port=ports["burst_port"],
            protocol="udp",
            session_id=session_id,
            recv_buffer_bytes=UDP_RECV_BUFFER_BYTES
        )

        # DL větev – řídicí smyčka
        self._dl_control = UdpControlLoop()
        self._dl_task = asyncio.create_task(
            self._dl_control.run(
                target_ip=obu_ip,
                local_port=ports["control_port"],
                session_id=session_id,
                interval_ms=effective.get("control_interval_ms", 100),
                packet_size=effective.get("control_packet_size", 256),
                payload_factory=self._mcm_factory,
            )
        )
```

---

### UC-D: OTA Software Update

| Parametr | Hodnota | Normativní reference |
|---|---|---|
| Standard | ISO 24089:2023 | |
| DL throughput | ≥ 0,4 Mbps | Odvozeno: 50 MB balík / 1000 s |
| Spolehlivost (app-level) | ≥ 99,0 % | Odvozeno z požadavku na integritu přenosu |
| Protokol | TCP | |
| Communication pattern | DL_ONLY | |
| Transfer size | 50 MB | |
| Chunk size | 64 KB | |
| default_duration_s | 300 | (self-terminating po dokončení přenosu) |

**Poznámka k normativním referenceím:** ISO 24089 definuje procesy OTA update, nikoliv konkrétní síťové KPI. Prahy 0.4 Mbps a 99.0% jsou odvozeny autorem jako minimální požadavky pro praktický OTA scénář (50 MB balík přenesený do přijatelného času s ověřitelnou integritou).

**Komunikační vzor:**
ITS-BO → OBU: TCP stream simulující SW update balík (50 MB, chunked 64 KB). Každý chunk obsahuje: `chunk_seq`, `md5_partial`, `data`. OBU → ITS-BO: per-chunk ACK s potvrzením integrity. Test se ukončí po přenosu všech chunků (self-terminating) nebo po timeoutu.

---

## 7. Transport Vrstva – Detailní specifikace

### 7.1 BurstReceiver (náhrada iPerf3 serveru)

```python
class BurstReceiver:
    """
    asyncio UDP/TCP server přijímající strukturované pakety od OBU.

    Payload formát příchozích paketů:
    [seq_number: 4B big-endian][timestamp_ns: 8B big-endian][uc_id: 2B][session_hash: 4B][data: NB]

    Klíčové vlastnosti:
    - SO_RCVBUF nastavený na 4 MB (konfigurabilní) – prevence kernel buffer overflow při 25 Mbps
    - Per-packet tracking: každý paket zalogován se seq, arrival timestamp, velikostí
    - Detekce chybějících seq čísel pro přesný packet loss
    - Monitorování /proc/net/udp pro detekci kernel drops

    Metodologie dle RFC 5357 (TWAMP):
    - Seq číslo v payloadu umožňuje detekci ztráty, duplikace i reorderingu
    - Timestamp v payloadu umožňuje jitter výpočet (variace inter-packet arrival)
    """

    async def start(self, port: int, protocol: str, session_id: str,
                    recv_buffer_bytes: int = 4194304):
        """
        Vytvoří UDP socket s rozšířeným receive bufferem.
        Spustí recv loop jako asyncio task.
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer_bytes)
        # Ověření skutečné velikosti bufferu (kernel může ořezat)
        actual_buf = self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        if actual_buf < recv_buffer_bytes:
            logger.warning(f"UDP buffer requested {recv_buffer_bytes} but got {actual_buf}. "
                          f"Zvyš net.core.rmem_max: sysctl -w net.core.rmem_max={recv_buffer_bytes*2}")
        self._sock.setblocking(False)
        self._sock.bind(("0.0.0.0", port))
        self._packets = []  # list of (seq, arrival_us, size, sender_timestamp_ns)
        self._bytes_received = 0
        self._start_time = time.monotonic()
        self._last_packet_time = time.monotonic()
        self._recv_task = asyncio.create_task(self._recv_loop(session_id))

    async def _recv_loop(self, session_id: str):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(self._sock, 65536), timeout=1.0
                )
                arrival_us = int(time.monotonic() * 1_000_000)
                self._last_packet_time = time.monotonic()
                # Parse header
                if len(data) >= 18:
                    seq = int.from_bytes(data[0:4], "big")
                    ts_ns = int.from_bytes(data[4:12], "big")
                    uc_id = int.from_bytes(data[12:14], "big")
                    self._packets.append((seq, arrival_us, len(data), ts_ns))
                    self._bytes_received += len(data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"BurstReceiver error: {e}")

    def get_stats(self, session_id: str) -> dict:
        elapsed_s = time.monotonic() - self._start_time
        if elapsed_s == 0:
            elapsed_s = 0.001

        # Packet loss: hledáme chybějící seq čísla
        if self._packets:
            seqs = sorted(p[0] for p in self._packets)
            expected_min, expected_max = seqs[0], seqs[-1]
            expected_count = expected_max - expected_min + 1
            missing = expected_count - len(seqs)
            loss_pct = (missing / expected_count * 100) if expected_count > 0 else 0

            # Jitter (RFC 3550): průměr |inter-arrival_n - inter-arrival_{n-1}|
            arrivals = [p[1] for p in self._packets]
            inter_arrivals = [arrivals[i+1] - arrivals[i] for i in range(len(arrivals)-1)]
            if len(inter_arrivals) > 1:
                jitter_values = [abs(inter_arrivals[i+1] - inter_arrivals[i])
                                for i in range(len(inter_arrivals)-1)]
                jitter_ms = sum(jitter_values) / len(jitter_values) / 1000
            else:
                jitter_ms = 0
        else:
            loss_pct = 100
            jitter_ms = 0
            missing = 0

        # Kernel drops monitorování
        kernel_drops = self._read_kernel_drops()

        return {
            "throughput_mbps": (self._bytes_received * 8) / elapsed_s / 1_000_000,
            "packet_loss_pct": loss_pct,
            "jitter_ms": round(jitter_ms, 3),
            "packets_received": len(self._packets),
            "packets_expected": len(self._packets) + missing,
            "bytes_received": self._bytes_received,
            "elapsed_s": round(elapsed_s, 2),
            "kernel_buffer_drops": kernel_drops,
            "recv_buffer_bytes_actual": self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
        }

    def _read_kernel_drops(self) -> int:
        """Čte /proc/net/udp pro socket drops."""
        try:
            inode = os.fstat(self._sock.fileno()).st_ino
            with open("/proc/net/udp") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 13 and parts[9] == str(inode):
                        return int(parts[12])
        except:
            pass
        return -1  # nedostupné
```

### 7.2 BurstSender

```python
class BurstSender:
    """
    asyncio UDP/TCP sender generující provoz dle UC profilu.
    Přesný inter-packet timing pomocí asyncio.sleep kompenzovaného o skutečný elapsed.
    """
    async def run(self, target_ip: str, target_port: int,
                  bitrate_mbps: float, packet_size: int,
                  payload_factory: Callable, session_id: str,
                  duration_s: float):
        """
        Vysílá pakety cílovým bitratem po dobu duration_s.
        payload_factory(seq) → bytes – generuje payload per paket.
        Inter-packet interval = (packet_size * 8) / (bitrate_mbps * 1e6) sekund.
        Kompenzace: pokud skutečný elapsed > plánovaný, příští sleep se zkrátí.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()

        interval_s = (packet_size * 8) / (bitrate_mbps * 1_000_000)
        seq = 0
        start = time.monotonic()
        next_send = start
        sent_bytes = 0
        send_times = []

        while time.monotonic() - start < duration_s:
            now = time.monotonic()
            if now < next_send:
                await asyncio.sleep(next_send - now)

            payload = payload_factory(seq)
            actual_send_time = time.monotonic()
            try:
                await loop.sock_sendto(sock, payload, (target_ip, target_port))
                sent_bytes += len(payload)
                send_times.append(actual_send_time)
            except Exception as e:
                logger.warning(f"BurstSender send error: {e}")

            next_send += interval_s
            seq += 1

        sock.close()

        # Send jitter výpočet
        if len(send_times) > 1:
            intervals = [send_times[i+1] - send_times[i] for i in range(len(send_times)-1)]
            deviations = [abs(i - interval_s) for i in intervals]
            send_jitter_ms = sum(deviations) / len(deviations) * 1000
        else:
            send_jitter_ms = 0

        return {
            "throughput_mbps_actual": (sent_bytes * 8) / (time.monotonic() - start) / 1_000_000,
            "throughput_mbps_target": bitrate_mbps,
            "send_jitter_ms": round(send_jitter_ms, 3),
            "packets_sent": seq,
            "bytes_sent": sent_bytes,
        }
```

### 7.3 AppLayerSimulator – Payload generátory

```python
class AppLayerSimulator:
    """
    Generuje UC-specifické payloady se sémanticky věrnou strukturou.
    """

    # ============ UC-A: CPM-like payload ============
    def build_cpm(self, seq: int, num_objects: int = 5) -> bytes:
        """
        Generuje CPM-like JSON payload dle ETSI TS 103 324 + TS 102 894-2.
        messageId = 14 (cpm) dle TR 103 562 B.2.2.
        protocolVersion = 1 dle TR 103 562 B.2.2.
        """
        cpm = {
            "header": {
                "messageId": 14,          # cpm dle TR 103 562
                "stationId": 1001,
                "referenceTime": int(time.time() * 1000),
                "protocolVersion": 1      # dle TR 103 562 B.2.2
            },
            "managementContainer": {
                "stationType": 5,         # passengerCar dle TS 102 894-2
                "referencePosition": {
                    "latitude": 501234560,   # WGS84, 1/10 micro degree
                    "longitude": 144567890,
                    "altitude": 25000        # 0.01 m units
                }
            },
            "perceivedObjects": [self._random_object(i, seq) for i in range(num_objects)]
        }
        raw = json.dumps(cpm).encode("utf-8")
        # Padding na 1600 B (normativní payload size R.5.4-001)
        if len(raw) < 1600:
            raw += b'\x00' * (1600 - len(raw))
        return raw[:1600]

    def _random_object(self, obj_id: int, seq: int) -> dict:
        """Generuje perceivedObject s variantními hodnotami per seq."""
        return {
            "objectId": obj_id,
            "timeOfMeasurement": -(seq % 100),  # ms, záporné = v minulosti
            "position": {
                "xDistance": 1500 + (seq * 10 + obj_id * 100) % 5000,  # 0.01m units
                "yDistance": 800 + (obj_id * 200) % 2000
            },
            "velocity": {
                "xVelocity": 1200 + (seq * 5) % 500,  # 0.01 m/s
                "yVelocity": 0
            },
            "objectAge": 0,
            "classification": [{"vehicleSubClass": 3, "confidence": 75}]
            # vehicleSubClass 3 = passengerCar dle TR 103 562
        }

    # ============ UC-A: Agregovaná mapa (DL) ============
    async def run_cpm_aggregation(self, target_ip, target_port, session_id,
                                   ul_receiver, aggregation_window_ms, tx_rate_hz):
        """
        Agregační smyčka: každých 1000/tx_rate_hz ms:
        1. Vezme objekty přijaté za posledních aggregation_window_ms
        2. Sloučí do jedné mapy (deduplikace per objectId, nejnovější vyhrává)
        3. Odešle zpět na OBU jako JSON
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()
        interval = 1.0 / tx_rate_hz
        seq = 0

        while True:
            await asyncio.sleep(interval)
            # Sestav agregovanou mapu z přijatých objektů
            aggregated = {
                "header": {"messageId": 14, "stationId": 9001, "aggregated": True,
                           "protocolVersion": 1, "seq": seq},
                "objects": []  # zde by se sloučily objekty z UL
            }
            payload = json.dumps(aggregated).encode("utf-8")
            try:
                await loop.sock_sendto(sock, payload, (target_ip, target_port))
            except:
                pass
            seq += 1

    # ============ UC-B: Video-like burst ============
    def build_video_gop(self, frame_seq: int) -> list[bytes]:
        """
        Vrátí list paketů pro jeden frame.
        I-frame (frame_seq % 30 == 0): ~50 KB → ~34 paketů po 1472 B
        P-frame: ~5 KB → 3-4 pakety
        """
        is_iframe = (frame_seq % 30 == 0)
        frame_size = 50000 if is_iframe else 5000
        frame_type = b'I' if is_iframe else b'P'

        # Header: [frame_type:1B][frame_seq:4B][gop_seq:4B][timestamp_us:8B]
        header = (frame_type +
                  frame_seq.to_bytes(4, "big") +
                  (frame_seq // 30).to_bytes(4, "big") +
                  int(time.monotonic() * 1_000_000).to_bytes(8, "big"))

        data = header + os.urandom(frame_size - len(header))
        # Fragment do 1472-byte paketů (MTU safe)
        return [data[i:i+1472] for i in range(0, len(data), 1472)]

    # ============ UC-C: MCM řídicí zpráva ============
    def build_mcm(self, seq: int, session_id: str) -> bytes:
        """
        Generuje MCM (Maneuvering Coordination Message) pro řídicí smyčku.
        Velikost: 256 B (paddováno).
        timestamp_us je z ITS-BO clock – bude použit pro RTT výpočet na příjmu ACK.
        """
        mcm = {
            "messageId": "MCM",
            "stationId": 9001,
            "seq": seq,
            "timestamp_us": int(time.monotonic() * 1_000_000),
            "control": {
                "steeringAngle": (seq * 2) % 360 - 180,  # variace pro realistický pattern
                "throttlePct": 15 + (seq % 10),
                "brakePct": 0,
                "gear": 4,
                "emergencyStop": False
            },
            "sessionId": session_id
        }
        raw = json.dumps(mcm).encode("utf-8")
        if len(raw) < 256:
            raw += b'\x00' * (256 - len(raw))
        return raw[:256]

    # ============ UC-D: OTA chunk ============
    def build_ota_chunk(self, chunk_seq: int, total_chunks: int,
                        package_id: str = "SW-v2.1.0-patch") -> bytes:
        """TCP chunk pro OTA update. 64 KB data + metadata JSON header."""
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
```

### 7.4 UdpControlLoop (UC-C DL řídicí smyčka)

```python
class UdpControlLoop:
    """
    Bidirectionální UDP pro UC-C řídicí smyčku.
    ITS-BO posílá MCM → OBU okamžitě odesílá ACK → ITS-BO měří RTT.

    RTT = ack_receive_time_us − mcm_send_time_us
    Obě timestamps z ITS-BO clock → nepotřebuje NTP synchronizaci.

    ACK payload od OBU: [seq:4B][ack_flag:1B (0xAC)][obu_processing_time_ns:8B]
    obu_processing_time_ns = čas od přijetí MCM do odeslání ACK na OBU straně (lokální měření)
    """

    async def run(self, target_ip: str, local_port: int, session_id: str,
                  interval_ms: int, packet_size: int, payload_factory: Callable):
        """
        Hlavní smyčka:
        1. Posílá MCM @ interval_ms Hz
        2. Současně přijímá ACK na stejném socketu
        3. Páruje ACK s MCM přes seq číslo
        4. Počítá RTT, jitter, loss
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)  # 1 MB
        sock.setblocking(False)
        sock.bind(("0.0.0.0", local_port))
        loop = asyncio.get_event_loop()

        self._sent_mcm = {}  # seq → send_timestamp_us
        self._rtt_samples = []
        self._packets_sent = 0
        self._acks_received = 0
        self._running = True
        interval_s = interval_ms / 1000

        # Paralelní send a receive
        send_task = asyncio.create_task(self._send_loop(
            sock, loop, target_ip, local_port + 1000, interval_s, payload_factory, session_id))
        recv_task = asyncio.create_task(self._recv_loop(sock, loop))

        self._send_task = send_task
        self._recv_task = recv_task

    async def _send_loop(self, sock, loop, target_ip, target_port, interval_s,
                         payload_factory, session_id):
        seq = 0
        start = time.monotonic()
        next_send = start
        while self._running:
            now = time.monotonic()
            if now < next_send:
                await asyncio.sleep(next_send - now)

            send_time_us = int(time.monotonic() * 1_000_000)
            payload = payload_factory(seq, session_id)
            self._sent_mcm[seq] = send_time_us

            try:
                await loop.sock_sendto(sock, payload, (target_ip, target_port))
                self._packets_sent += 1
            except Exception as e:
                logger.warning(f"MCM send error: {e}")

            next_send += interval_s
            seq += 1

    async def _recv_loop(self, sock, loop):
        while self._running:
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 4096), timeout=1.0)
                recv_time_us = int(time.monotonic() * 1_000_000)
                # Parse ACK: [seq:4B][ack_flag:1B][obu_processing_ns:8B]
                if len(data) >= 13 and data[4] == 0xAC:
                    ack_seq = int.from_bytes(data[0:4], "big")
                    obu_processing_ns = int.from_bytes(data[5:13], "big")
                    if ack_seq in self._sent_mcm:
                        rtt_us = recv_time_us - self._sent_mcm[ack_seq]
                        self._rtt_samples.append({
                            "seq": ack_seq,
                            "rtt_us": rtt_us,
                            "obu_processing_us": obu_processing_ns / 1000,
                            "recv_time_us": recv_time_us,
                        })
                        self._acks_received += 1
            except asyncio.TimeoutError:
                continue

    def get_stats(self, session_id: str) -> dict:
        if not self._rtt_samples:
            return {"avg_rtt_ms": None, "p95_rtt_ms": None, "p99_rtt_ms": None,
                    "packets_sent": self._packets_sent, "acks_received": 0}

        rtts_ms = sorted([s["rtt_us"] / 1000 for s in self._rtt_samples])
        n = len(rtts_ms)
        return {
            "avg_rtt_ms": round(sum(rtts_ms) / n, 3),
            "min_rtt_ms": round(rtts_ms[0], 3),
            "max_rtt_ms": round(rtts_ms[-1], 3),
            "p50_rtt_ms": round(rtts_ms[int(n * 0.5)], 3),
            "p95_rtt_ms": round(rtts_ms[int(n * 0.95)], 3),
            "p99_rtt_ms": round(rtts_ms[int(n * 0.99)], 3),
            "jitter_ms": round(self._calc_jitter(rtts_ms), 3),
            "packet_loss_pct": round((1 - self._acks_received / max(self._packets_sent, 1)) * 100, 4),
            "packets_sent": self._packets_sent,
            "acks_received": self._acks_received,
            "control_loop_hz_actual": round(self._packets_sent / max(self._elapsed_s(), 0.001), 2),
            "rtt_sample_count": n,
        }

    def _calc_jitter(self, sorted_rtts) -> float:
        if len(sorted_rtts) < 2:
            return 0
        diffs = [abs(sorted_rtts[i+1] - sorted_rtts[i]) for i in range(len(sorted_rtts)-1)]
        return sum(diffs) / len(diffs)
```

### 7.5 BaselineRunner

```python
class BaselineRunner:
    """
    Referenční baseline měření. Spouští se před testovací session.
    OBU iniciuje baseline přes POST /api/v1/baseline/start.
    ITS-BO spustí receiver, OBU provede burst, výsledky sdílí zpět.

    Zjednodušená varianta: baseline je jen ICMP ping (10× z ITS-BO na OBU IP).
    Pokud OBU nepodporuje ping (ICMP filtrovaný), baseline = "unavailable".
    """
    async def run_ping_baseline(self, obu_ip: str) -> dict:
        """10× ICMP ping, 200ms interval."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "10", "-i", "0.2", "-W", "1", obu_ip,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            # Parse ping output pro avg RTT
            output = stdout.decode()
            # Hledáme "rtt min/avg/max/mdev = X/Y/Z/W ms"
            for line in output.split('\n'):
                if 'avg' in line and '/' in line:
                    parts = line.split('=')[1].strip().split('/')
                    return {
                        "status": "completed",
                        "ping_rtt_min_ms": float(parts[0]),
                        "ping_rtt_avg_ms": float(parts[1]),
                        "ping_rtt_max_ms": float(parts[2]),
                        "ping_rtt_mdev_ms": float(parts[3].replace(' ms', '')),
                    }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
        return {"status": "no_response"}
```

---

## 8. REST API

### 8.1 Kompletní endpointy

| Endpoint | Metoda | Popis |
|---|---|---|
| `/api/v1/profiles` | GET | Dynamický seznam UC profilů z plugin loaderu |
| `/api/v1/session/init` | POST | OBU inicializuje session |
| `/api/v1/session/start` | POST | OBU spustí test |
| `/api/v1/session/stop` | POST | OBU ukončí test, vrátí výsledky |
| `/api/v1/session/status/{session_id}` | GET | SSE stream live metrik (1s interval) |
| `/api/v1/baseline/start` | POST | Připraví ITS-BO pro baseline příjem |
| `/api/v1/baseline/result` | POST | OBU nahraje baseline výsledky |
| `/api/v1/results/{session_id}` | GET | Kompletní JSON výsledek |
| `/api/v1/results/history` | GET | Seznam všech výsledků, desc |
| `/api/v1/system/status` | GET | Plugin status, porty, uptime |

### 8.2 POST /api/v1/session/init – request

```json
{
  "uc_id": "UC-C",
  "obu_ip": "192.168.3.2",
  "label": "Test run 1 – indoor lab, NR NSA",
  "network_condition": "lab_amarisoft_5g_nsa",
  "lab_config": {
    "bandwidth_mhz": 20,
    "qos_class": "default",
    "competing_load_mbps": 0,
    "amarisoft_config": "gnb-nsa.cfg",
    "notes": "NR NSA, indoor, no interference"
  },
  "params": {},
  "requested_duration_s": 60,
  "obu_app_version": "1.0.0"
}
```

### 8.3 POST /api/v1/session/init – response

```json
{
  "session_id": "UC-C-20260318-142301-a7f2",
  "server_ready": true,
  "allocated_ports": {
    "burst_port": 5100,
    "control_port": 4500
  },
  "effective_params": {
    "packet_size_bytes": 256,
    "control_interval_ms": 100,
    "ul_bitrate_mbps": 25,
    "duration_s": 60
  },
  "duration_s": 60,
  "preflight_warnings": []
}
```

**effective_params** je autoritativním zdrojem parametrů. OBU MUSÍ použít tyto hodnoty, ne své lokální defaults. Toto řeší problém parametrické synchronizace.

### 8.4 POST /api/v1/session/stop – request (rozšířený)

```json
{
  "session_id": "UC-C-20260318-142301-a7f2",
  "obu_stats": {
    "packets_sent": 98452,
    "bytes_sent": 147678000,
    "send_jitter_ms": 1.8,
    "gc_pause_detected": false,
    "platform_overhead": {
      "send_jitter_ms": 1.8,
      "max_inter_packet_gap_ms": 52.3
    }
  }
}
```

OBU posílá `obu_stats` v session/stop. ITS-BO je použije pro `packet_delivery_ratio` výpočet a uloží do výsledku.

### 8.5 Schéma výsledku (JSON) – kompletní

```json
{
  "test_id": "UC-C-20260318-142301-a7f2",
  "uc_profile": "UC-C",
  "uc_name": "Tele-Operated Driving",
  "standard_reference": "3GPP TS 22.186 v18.0.1 Table 5.5-1 [R.5.5-002]",
  "session_status": "COMPLETED",
  "network_condition": "lab_amarisoft_5g_nsa",
  "lab_config": {
    "bandwidth_mhz": 20,
    "amarisoft_config": "gnb-nsa.cfg"
  },
  "label": "Test run 1 – indoor lab",
  "started_at": "2026-03-18T14:23:01Z",
  "duration_s": 60,
  "duration_actual_s": 59.8,
  "obu_ip": "192.168.3.2",
  "effective_params": {
    "control_interval_ms": 100,
    "control_packet_size": 256,
    "ul_bitrate_mbps": 25
  },
  "baseline": {
    "status": "completed",
    "ping_rtt_avg_ms": 9.4,
    "ping_rtt_min_ms": 8.1,
    "ping_rtt_max_ms": 14.2
  },
  "measured": {
    "ul": {
      "throughput_mbps": 23.1,
      "jitter_ms": 0.8,
      "packet_loss_pct": 0.001,
      "packets_received": 98450,
      "bytes_received": 147675000,
      "kernel_buffer_drops": 0
    },
    "dl": {
      "avg_rtt_ms": 12.4,
      "min_rtt_ms": 6.2,
      "max_rtt_ms": 34.1,
      "p50_rtt_ms": 11.8,
      "p95_rtt_ms": 18.7,
      "p99_rtt_ms": 24.1,
      "jitter_ms": 1.2,
      "packet_loss_pct": 0.002,
      "packets_sent": 600,
      "acks_received": 598,
      "control_loop_hz_actual": 9.97,
      "rtt_sample_count": 598
    }
  },
  "obu_reported_stats": {
    "packets_sent": 98452,
    "send_jitter_ms": 1.8,
    "gc_pause_detected": false
  },
  "packet_delivery_ratio_pct": 99.998,
  "normative_thresholds": {
    "e2e_latency_ms": {"value": 5, "op": "<=", "ref": "R.5.5-002"},
    "application_reliability_pct": {"value": 99.999, "op": ">=", "ref": "R.5.5-002"},
    "ul_throughput_mbps": {"value": 25, "op": ">=", "ref": "R.5.5-002"},
    "dl_throughput_mbps": {"value": 1, "op": ">=", "ref": "R.5.5-002"}
  },
  "evaluation": {
    "e2e_latency_ms": {
      "measured": 6.2, "threshold": 5, "op": "<=",
      "pass": false, "ref": "R.5.5-002",
      "note": "E2E latence aproximována jako RTT/2 měřeno na ITS-BO"
    },
    "application_reliability_pct": {
      "measured": 99.998, "threshold": 99.999, "op": ">=",
      "pass": false, "ref": "R.5.5-002",
      "note": "Měřeno na aplikační vrstvě (přísnější než L2/L3 definice 3GPP)"
    },
    "ul_throughput_mbps": {
      "measured": 23.1, "threshold": 25, "op": ">=",
      "pass": false, "ref": "R.5.5-002"
    },
    "dl_throughput_mbps": {
      "measured": 0.997, "threshold": 1, "op": ">=",
      "pass": false, "ref": "R.5.5-002"
    }
  },
  "overall_pass": false,
  "interpretation": "FAIL – Síť nesplňuje UC-C požadavky. Nesplněné metriky: e2e_latency_ms: naměřeno 6.2 (RTT/2), požadavek <= 5 [R.5.5-002]; application_reliability_pct: naměřeno 99.998, požadavek >= 99.999 [R.5.5-002]; ul_throughput_mbps: naměřeno 23.1, požadavek >= 25 [R.5.5-002]."
}
```

---

## 9. Frontend – Next.js 14

### 9.1 Design principy

- Dark theme, profesionální laboratorní estetika
- Primary: `#3B82F6` (blue) | PASS: `#22C55E` | FAIL: `#EF4444` | WARNING: `#F59E0B`
- Monospace font pro IP adresy, naměřené hodnoty a raw JSON
- Optimalizováno pro 1920×1080 desktop
- Responsivní na 1366×768

### 9.2 Stránky

| Stránka | URL | Obsah |
|---|---|---|
| Test Panel | `/test` | Hlavní ovládací panel – výběr UC, konfigurace, live monitoring |
| Session Monitor | `/session/[id]` | Live monitoring aktivní session (SSE) |
| Historie | `/results` | Tabulka + filtry (UC, network_condition, pass/fail, datum) |
| Detail | `/result/[id]` | Detailní výsledek jednoho testu |
| Analytics | `/analytics` | Agregované grafy přes všechny testy |

### 9.3 Layout /test – třípanelový

**LEVÝ PANEL (30 %) – Výběr UC:**
- Karty UC načteny z `/api/v1/profiles`
- Karta: UC ID badge | název | standard reference | klíčové prahy
- Vybraná karta: modrý border
- Pod kartami: plugin status (✅ loaded / ❌ error + důvod)

**STŘEDNÍ PANEL (40 %) – Konfigurace:**
- UC profil header s normativní referencí
- Network condition dropdown: `lab_amarisoft_lte` | `lab_amarisoft_5g_nsa` | `field_tmobile_4g` | `field_o2_4g` | `field_vodafone_4g` | `field_tmobile_5g` | `custom`
- Lab config: bandwidth, QoS, competing load, Amarisoft config
- Test label input
- Duration dropdown: 30s | 60s | 120s | 300s
- Collapsible parameter overrides (s jednotkami a normativní referencí)
- **Session status box:** WAITING / BASELINE / RUNNING / COMPLETED / INTERRUPTED / ERROR
- Baseline výsledky (pokud provedeny)

**PRAVÝ PANEL (30 %) – Live Status (SSE):**
- Session ID + status + elapsed timer
- Baseline kontext
- Live UL metriky (throughput, loss, packets)
- Live DL metriky (RTT avg/p50/p95, jitter, loss)
- Normativní prahy jako referenční linky
- Červené zvýraznění překročení prahu v reálném čase
- Kernel buffer drops warning (pokud >0)

### 9.4 Detail výsledku /result/[id]

- Velký PASS/FAIL badge s `interpretation` textem
- `session_status` badge (COMPLETED / INTERRUPTED s důvodem)
- Baseline context sekce
- Tabulka: metrika | normativní práh | naměřeno | p95 | PASS/FAIL | ref | note
- Packet delivery ratio (OBU sent vs. ITS-BO received)
- Lab config metadata
- effective_params sekce
- Raw JSON (expandovatelný + copy button)
- Export: JSON + CSV

---

## 10. Logování a debugging

### 10.1 Strukturovaný log systém

```python
import logging

# Tříúrovňový log – každý session má vlastní log soubor
# logs/{session_id}.log – OPERATIONAL + TECHNICAL
# logs/{session_id}_debug.log – DEBUG (raw pakety)

logger = logging.getLogger("itsbo")

class SessionLogger:
    """Per-session logger. Vytváří soubor logs/{session_id}.log"""
    def log(self, level: str, layer: str, event: str, data: dict = None):
        """
        level: "OPERATIONAL" | "TECHNICAL" | "DEBUG"
        layer: "TRANSPORT" | "UC_ENGINE" | "SESSION" | "API"
        """
        entry = {
            "timestamp_us": int(time.monotonic() * 1_000_000),
            "level": level,
            "layer": layer,
            "event": event,
            "data": data or {}
        }
        # Zápis do souboru + Python logger
```

---

## 11. Quality Gates

- Každý normativní práh trasovatelný k přesnému článku standardu
- Thresholds immutable za runtime (frozen dataclass)
- Žádné hardcoded IP adresy – vše přes config.py / env vars
- Backend nastartuje i bez pluginů (prázdný plugin list)
- Výsledky jako JSON soubory (žádná databáze)
- Žádná autentizace
- Žádný Docker
- Žádné ASN.1 kódování, GeoNetworking, BTP
- `evaluation.interpretation` vždy přítomno a srozumitelné
- `effective_params` v session/init response – OBU je musí respektovat
- `session_status` vždy reflektuje skutečný stav (včetně INTERRUPTED)
- `packet_delivery_ratio_pct` v každém výsledku kde OBU reportuje packets_sent

---

## 12. Deployment

### 12.1 install.sh

```bash
#!/bin/bash
set -e

echo "=== ITS-BO Test Platform – instalace ==="

# 1. Systémové požadavky
sudo sysctl -w net.core.rmem_max=8388608
sudo sysctl -w net.core.rmem_default=4194304
echo "net.core.rmem_max=8388608" | sudo tee -a /etc/sysctl.d/99-itsbo.conf
echo "net.core.rmem_default=4194304" | sudo tee -a /etc/sysctl.d/99-itsbo.conf

# 2. Python backend
pip install -r requirements.txt --break-system-packages

# 3. Node.js frontend
cd ../its-bo-frontend && npm install && npm run build && cd ../its-bo-backend

# 4. Adresáře
mkdir -p results logs

# 5. Statická route (lab only – zakomentovat pro VPS)
# sudo ip route add <UE_SUBNET>/24 via <CALLBOX_IP>
# Pro persistenci přidat do /etc/netplan/

# 6. Firewall (VPS only)
# sudo ufw allow 8000/tcp
# sudo ufw allow 3000/tcp
# sudo ufw allow 4500:5200/udp

# 7. Systemd
sudo cp itsbo-backend.service /etc/systemd/system/
sudo cp itsbo-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now itsbo-backend itsbo-frontend

echo "=== Hotovo. Backend: http://$(hostname -I | awk '{print $1}'):8000 ==="
```

### 12.2 requirements.txt

```
fastapi>=0.104
uvicorn[standard]>=0.24
aiofiles
pydantic>=2.0
```

### 12.3 Systemd služby

**itsbo-backend.service:**
```ini
[Unit]
Description=ITS-BO Backend
After=network.target

[Service]
Type=simple
User=itsbo
WorkingDirectory=/home/itsbo/its-bo-backend
ExecStart=/usr/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment=ITSBO_RESULTS_DIR=/home/itsbo/its-bo-backend/results

[Install]
WantedBy=multi-user.target
```
