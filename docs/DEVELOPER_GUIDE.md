# ITS-BO & ITS-OBU: Developer Architecture & Integration Guide
Tento dokument slouží jako vysoce pokročilá technická a architektonická specifikace softwarového řešení ITS-BO (Back-Office) a ITS-OBU (On-Board Unit). Je určen výhradně pro software engineery, síťaře a budoucí vývojáře, kteří budou do systému doplňovat moduly a potřebují pochopit asynchronní komunikační vrstvy.

---

## 1. High-Level Architektura Systemu

Systém je koncipován jako distribuované asymetrické řešení typu **High-Volume Client & Real-time Aggregator**. 
Sestává se z mobilní stanice (Android), která za běhu chrlí telemetrická UDP a JSON TCP data do centralizovaného Linux serveru, který je neblokujícím (asynchronním) způsobem streamuje přes Server-Sent Events (SSE) do moderního Reactího frontendu.

```mermaid
graph TD
    subgraph "ITS-OBU (Android Client)"
        UI[Jetpack Compose UI] --> VM[ViewModels]
        VM <--> Rep[Coroutines Repository]
        Rep <--> SVC[Foreground Service & WakeLock]
        SVC -->|UDP 4567| TL[Control Loop UdpSocket]
        SVC -->|UDP 5100| BR[Burst Emitter UdpSocket]
        SVC -->|TCP 8000 (HTTP/JSON)| REST[Retrofit/OkHttp]
    end

    subgraph "ITS-BO (Ubuntu Server)"
        TL -.->|Keep-Alive| BO_C[UDP Listener 4567]
        BR -.->|High-Volume Payload| BO_B[UDP Burst Receiver 5100]
        REST ==>|Test Start/Stop/Export| API[FastAPI REST API 8000]
        
        API <-->|State/Aggregator| DB[(File System JSON Store / DB)]
        BO_C -->|Push Event| EM[Event Manager SSE]
        BO_B -->|Push Event| EM
        API -->|Register SSE| EM
    end

    subgraph "ITS-BO Frontend (Next.js)"
        EM ==>|SSE stream (TCP 8000)| FW[Next.js API Routes]
        FW --> CC[React Client Components]
        CC --> GH[Recharts / D3.js Charts]
    end
```

---

## 2. ITS-OBU (Android Client) - Technologický Stack

Klient je postaven v Kotlinu pro moderní API 30+ s těmito klíčovými stavebními bloky:

### 2.1 Concurrency & Lifecycle Management
- Vzhledem k extrémní zátěži (desítky tisíc requestů na síť za minutu) je kompletní síťová vrstva odbavována skrz **Kotlin Coroutines** na `Dispatchers.IO` poolu. 
- Aby Android OS nezabil testovací smyčku kvůli agresivní správě paměti a baterie (Doze Mode), celý test běží obalený do **Android Foreground Service** (konkrétně `Service` s notifikačním kanálem `IMPORTANCE_DEFAULT`). Notifikace používá implicitní mapování `Intent` přes explicitní definici `.MainActivity`, jelikož Android 12 vyžaduje `FLAG_IMMUTABLE` pro PendingIntents z pozadí.
- Systém dále využívá instanciované `PowerManager.WakeLock` (úroveň `PARTIAL_WAKE_LOCK`), které je striktně drženo pouze po dobu aktivního testování.

### 2.2 Deklarativní UI
Frontend aplikace nevyužívá staré `XML` layouty. Je implementovaný pomocí **Jetpack Compose**. Modely drží state přes immutable stavové proměnné (StateFlow), čímž je dosaženo UDF (Unidirectional Data Flow).

---

## 3. ITS-BO (Linux Server Backend)

### 3.1 FastAPI & Asynchronní I/O
Serverové jádro je napsáno v Python 3.12 nad frameworkem **FastAPI** a asynchronním serverem **Uvicorn** (`uvloop` event loop modifikace pro max C-level výkon).

- Veškeré API endpointy jsou definovány s prefixem `async def` a využívají vestavěnou FastApi podporu vrácení asynchronních generátorů.
- **Server-Sent Events (SSE):** Zobrazování živých dat přes protokol `text/event-stream`. Klient (Next.js prohlížeč) provede 1 neukončený HTTP GET požadavek (např. `/stream/live`) na FastAPI endpoint vracející generátor dat. Ten přes `asyncio.sleep` či `Queue.get()` tlačí periodicky nová data.

### 3.2 Network Sockets (UDP Burst)
Architektura se nespoléhá plně na TCP z důvodu nutnosti měření jitteru, latence a paketových ztrát.
Při zátěžových scénářích ("Burst testech") běží pod standardním Python `asyncio` čisté sokety:
- **Port 5100 (Burst Receiver):** Běží vlastní nekonečná smyčka (`Transport` protocol). Přijímá nefiltrované byty od klienta a na základě serializované sekvence poznává přeskočená ID balíčků (Packet loss detection).
- Konfigurace Bufferů: Jelikož CPython neumí efektivně číst miliardu UDP bufferů z jádra za sekundu před tím, než jádro smaže staré stacky, inicializační skript nastavuje systémové konstanty Linuxu: `net.core.rmem_max=8388608` (8 MB UDP ring buffery) pro zachování integrity paketu před Python zpracováním.

---

## 4. ITS-BO Frontend (Next.js)

Vizuální vrstva je postavena na frameworku Next.js verzi 14+ (`App Router`) se silným zaměřením na Server Side Rendering (SSR) a responzivitu v prostředí laboratoře.

### 4.1 React & State
Celá dashboard aplikace používá Single Page Application (SPA) paradigma se specifikovaným "Dark Mode" UI postaveným přes **Tailwind CSS**.
- Reaktivita grafů: Implementována knihovnou **Recharts** (wrapper kolem D3). Grafy přijímají přes React Hooks např. `useEffect()` nová pole `json` objektů doručených ze SSE streamu. Pole state manageru si udržují fixní délku (kruhový buffer o velikosti X uzlů) a mažou stará data operací typu `Array.prototype.slice(-X)`, což drží garbage collector a V8 prohlížeče v optimálních latencích bez memory leaků.

---

## 5. Security & Sítová Propustnost

Projekt v základu cílí na testovací prostředí ITS, nikoli korporátní banking, proto není uplatněna OAuth autentizace přes OIDC ani certifikáty mTLS na straně UDP, ale:
1. Rozsah API je mapován za striktní stavovou bariéru. Pokud nebylo voláno endpointem započetí testu (Session Start), UDP handlery veškeré cizí burst pakety na socket vrstvě mažou (DDoS protection measure).
2. Ochrana systému Linux je zálohována pravidly vrstvy UFW pro striktní výčet poslouchaných portů (TCP: 8000, 3000; UDP: 4500-4599, 5100-5200).

---

## 6. Implementační Moduly & Codebase Navigace

Pro budoucí údržbu kódu zvažujte logiku uložených modulů:
- **Vlákno Sběru UDP Dat:** Třídy zodpovědné za deserializaci `bytearray` leží v `its-bo-backend/core/udp`. Nemenit serializační model (Endianitu, Padding) bez propisu do `ITS-OBU` Kotlin serializéru (v Kotlinu často natvrdo specifikovaný přes `ByteBuffer.order(ByteOrder.BIG_ENDIAN)`).
- **Session management:** Aktuální stav systému je udržován in-memory ve FastAPI Dependency Injecion kontejnerech. Pokud by systém do budoucna musel zvládat multi-threading uvicorn workerů (`--workers 4`), musel by se přejednat stav z in-memory singletonu do instance sdíleného Redis serveru. Nyní běží na 1 workeru a škáluje v rámci Asynchronního I/O.
