# 📖 ITS-BO & ITS-OBU: Codebase Reference & Deep Dive

Tento dokument funguje jako ultimátní průvodce mozkem celého systému. Umožní jakémukoliv budoucímu vývojáři přesně pochopit logiku, na níž je celá diplomová (C-ITS) telemetrická větev postavena. Detailně rozebírá klíčové funkce, ošetřování chyb a konkrétní asynchronní smyčky ve všech třech zásadních částech repozitáře.

---

## 1. Topologie repozitáře a Datový Model

Celý projekt je fyzicky rozseknutý na tři de-facto samostatné, ale funkčně provázané systémy:
1. `its-obu-app/` – Nativní Android aplikace (Kotlin) suplující jednotku v autě.
2. `its-bo-backend/` – Těžké matematicko-síťové API v Pythonu.
3. `its-bo-frontend/` – Lehká prezentační web-app vrstva v TypeScriptu.

### Tok Dat (The Data Flow Paradigm)
Komunikace mezi těmito složkami není synchronní (tedy klient nečeká na odpověď, než pošle další požadavek). Funguje výlučně modelem "Fire-and-Forget":
1. Android si přes HTTP/TCP (`POST /api/v1/sessions/start`) zažádá o jedinečné `session_id`.
2. Asynchronní IO thready v Androidu otevřou `DatagramSocket` obalující neodeslané UDP krabičky (Bursty).
3. Do struktury UDP balíčku se vkládá minimální možný Payload (Byte Array). Každý Burst paket typicky nese své interní sekvenční číslo a klientský Timestamp, díky čemuž UDP backend na Linuxu přesně pozná, co se ztratilo (Packet Loss = `Max_Ocekavane_ID - Prijate_ID`).
4. Po dokončení měření nahraje Android skrz HTTP svůj finální, přesně zkompilovaný JSON profil do `/api/v1/sessions/{id}/stop`, ze kterého se stane trvalý záznam na disku.

---

## 2. Kód ITS-OBU: Android (Kotlin / Coroutines)

Aplikace OBU neřeší estetiku, je to čistý těžký klient uzpůsobený na přežití procesu na pozadí. V této složce je kód navržen tak, aby obešel restrikce moderního Android OS vůči zabíjení baterie (Doze mody).

### 2.1 UI Vrstva (Jetpack Compose)
Aplikace nepoužívá staré XML diagramy a `findViewById`. Stojí čistě na deklarativní syntaxi v `/app/src/main/java/cz/cvut/fel/itsobu/ui`.

* **`SettingsScreen.kt` & Datové centrum:**  
Zde se zadávají API a Porty laboratoře. Protože by nebylo dobré ztrácet adresu pokaždé, co se telefon zamkne, všechna textová pole ukládají svůj stav do Androidího mechanismu *DataStore* (případně *SharedPreferences*). Reakce mezi psaním textu a vykreslením propisuje *StateFlow*.
* **Pohyb dat z UI do Servicy:** UI samo o sobě neprovádí měření! Když uživatel v UI klikne "START MĚŘENÍ", UI zabalí zadané IP adresy do speciální zprávy zvané `Intent` a pošle tento `Intent` směrem do jádra Androidu pro probuzení naší Service vrstvy na pozadí.

### 2.2 Srdce aplikace: `TestForegroundService.kt`
Nejkritičtější soubor celé mobilní aplikace. Jelikož moderní Android agresivně zabíjí všechno, na co se zrovna uživatel na obrazovce nedívá, obalili jsme běh kódu do institutu *Služby na popředí*.

```kotlin
// Ukázka základní definice služby
class TestForegroundService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null
```

* **Notifikační záchrana (`FLAG_IMMUTABLE`):** Od Androidu verze 12 (SDK 31+) systém nedovoluje zapnout Background službu, pokud o tom neví uživatel. Musíme mu nahoru do notifikační lišty vyvěsit upozornění "Měřím data!". Toto upozornění otevírá aplikaci kliknutím zpět – to se řeší přes `PendingIntent`, u kterého musíte v našem repozitáři od nového API 31+ vždy specifikovat flag pro jeho trvalost `FLAG_IMMUTABLE`. 
* **Zlatý grál: `WakeLock`:** Když zhasnete diplej telefonu v kapse, Android do 5 minut zastaví (uspí) procesor telefonu (tzv. *Deep Sleep*). V tu chvíli by UDP měření zamrzlo. V kódu Proto při startu testu voláme `WakeLock.PARTIAL_WAKE_LOCK`. Získáváme od jádra "Povolení neusnout". I při černém displeji běží procesor u nás naplno. Jakmile uživatel v aplikaci klikne na "STOP", zámek se uvolní (`wakeLock?.release()`).
*(Bez tohoto by byly veškeré dlouhé testy v terénu okamžitě mrtvé).*

### 2.3 Síťová propustnost a Coroutines (`网络 / UDP vrstva`)
Sběr i odesílání tisíců bitů zajišťujeme souběžně přes asynchronní knihovnu v Kotlinu (Coroutines). Odesílací smyčka nespí primárním `Thread.sleep()`, ale používá `delay(x)` z Korutin na modifikátoru `Dispatchers.IO` (vlákna vyhrazená v C++ pro práci se sítí a diskem).

```kotlin
// Koncept UDP Push smyčky
val udpSocket = DatagramSocket()
coroutineScope.launch(Dispatchers.IO) {
    while(isActive && testIsRunning) {
        val payload = generateByteArray(packetId, timestamp)
        val packet = DatagramPacket(payload, payload.size, InetAddress.getByName(ip), port)
        udpSocket.send(packet)
        delay(burstIntervalMs) // Počká např 2 ms a jede znovu
    }
}
```

---

## 3. Kód ITS-BO Backend: The Data Cruncher (FastAPI)

Architektura backendu v `its-bo-backend/` nepoužívá Django ani Flask, protože ty historicky blokují (Gunicorn/WSGI) jedno vlákno na jeden příchozí request. Zvolili jsme **FastAPI**, které je zespodu psané plně nad asynchronním `async/await` cyklem (ASGI). Proč? Protože musíme přijímat miliardu UDP paketů a současně non-stop streamovat Live grafy tisícům připojených webových portálů.

### 3.1 UDP vrstva: Jak chytáme Burst testy on the fly
Samotný `uvicorn` neumí od výroby chytat UDP byty, zabývá se jen TCP HTTP hlavičkami. Proto si v souboru `core/udp/burst_receiver.py` píšeme vlastní Pythoní smyčku.

Třída využívá rozhraní `asyncio.DatagramProtocol`.
- Event smyčka `uvloop` (C modul dodaný Uvicornem) nám při dopadu nového UDP datagramu vyvolá callback `datagram_received()`. A od té chvíle běží čas!
- Kód přečte byty, rozluští z oněch bajtů naši strukturu identifikátoru a časového razítka a provede základní matematickou rovnici: *(Kolikátý paket jsem teď čekal)* mínus *(Kolikátý mi reálně z telefonu dopadl)*. Rozdíl těchto dvou čísel rovnou loguje za běhu jako ZTRACENÝ (`Packet Loss`).
- Následně zprávu a statistiky vezme, nacpe je do stavového in-memory Slovníku (`SessionManager`) a předkopne ho Webovým klientům.
- *Změna Kernelu v install.sh:* Všechny tyto výpočty by C++ smyčka sice stihla, ale defaultně nastavený Linux (Ubuntu) má pro UDP vyhrazené vnitřní fronty o šířce mrňavých 200 KB. Když z telefonu padají pakety po kilech a Python nestíhá, pamětní `ring_buffer` přeteče a **ztrátu způsobí přímo samotný síťový port Ubuntu ještě dřív, než Python vůbec zjistí, že data přišla.** Tady naráží programátor kódové vrstvy na zeď operačního systému. Právě proto náš instalační skript přetáčí linuxovou konstantu `sysctl -w net.core.rmem_max=8388608` z 200 KB rovnou na obříh 8 MB. 

### 3.2 SSE Event Manager: Transport k Live Grafům
Data jsou zachycena, dekódována, ztráta spočítána. Jak to dostaneme ze serveru uživateli na modrý webový monitor do vedlejšví místnosti, aniž by prohlížeč musel klikat F5 (refresh)?
Místo těžkých WebSocketů se použil ideální streamovací vzor **Server-Sent Events** v souboru `event_manager.py`.

```python
async def event_generator(self, request: Request):
    try:
        while True:
            if await request.is_disconnected():
                break
            # Z queue si vytáhneme naporcovaná nová JSON data
            data = await self.queue.get()
            yield f"data: {json.dumps(data)}\n\n"
    except asyncio.CancelledError:
        pass
```
FastAPI přes generátor `yield` tlačí jeden string za druhým, a HTTP žádost v tu chvíli de-facto stále probíhá s nekonečnou délkou, takže ji prohlížeč neusekne, a místo toho rovnou kreslí.

---

## 4. Kód ITS-BO Frontend: Neuhasitelný Dashboard (Next.js)

Projekt leží v `its-bo-frontend/`. Next 14 Framework zde plní primárně layout a routing do komponenty s grafy. 

### 4.1 React State vs. Garbage Collector (Záludnost pole)
Zobrazení je plně responsivní (TailwindCSS) – jádro vizuálu leží v `/components/`. Na vizuální graf používáme React knihovnu `Recharts`.
Zásadním problémem každého live-stream webu je spotřeba operační paměti (RAM) uživatelova webového prohlížeče Chrome. Kdybychom s každým dalším přijatým Eventem skrz Hook `setGraphData(prev => [...prev, newData])` slepovali další položky, po deseti minutách zátěžového OBU měření bude mít pole grafu desítky tisíc hodnot a tab v Chromu celou laboratoř kompletně zasekne pro vyčerpání paměti (Lag of Death).

Řešení tohoto kódu spočívá v **Cyklické frontě (Circular Buffer)** rovnou v Reactu. Pokaždé, když ze serverového SSE endpointu dorazí nové živé číslo (ztrátovost, packet count atp.), zavoláme obalený array `.slice(-MAX_UKAZATELU)`:

```typescript
useEffect(() => {
    const eventSource = new EventSource(`${apiUrl}/api/v1/stream/live`)
    
    eventSource.onmessage = (event) => {
        const parsedData = JSON.parse(event.data)
        setGraphData(prevData => {
            const newArray = [...prevData, parsedData]
            // Paměťový chránič - Udrž v renderu pouze posledních 100 hodnot!
            return newArray.length > 100 ? newArray.slice(newArray.length - 100) : newArray
        })
    }
    
    // Čistící unmount! Bez tohoto by refresh okna vytvořil druhého SSE číšníka
    return () => eventSource.close()
}, [])
```
Obrázek grafu na monitoru v certifikované laboratoři se tedy bude neustále promazávat (vykreslujíc pouze 100 nejnovějších plošek za sebou) a díky tomu frontend vydrží bez padání nekonečně dlouhou monitorovací šichtu.

---

## 5. Zdroje, Omezení a Future Work
Znalosti obsažené v tomto souboru přesně definují hranice celého ekosystému.
Pokud by v budoucnu byla vyžadována drasticky vyšší zátěž (např 10 aut současně, každé střílející z UDP soketů maximálně přes `Dispatchers.IO`), vývojář by musel sáhnout do Uvicornu a spustit jej přes `--workers 4`. Avšak! Multi-processing zabije náš nynější `in-memory Session Manager` slovník (každý process si natáhne svůj separátní memory-leak thread a nedokážou o sobě v OŠ mluvit).  
**Budoucí řešení:** V momentě aktivace více workerů k Uvicornu musí být state přesunut z lokálního slovníku Dictionary na instanci externí **Redis** Cache databáze! Pro jednovozidlové iterace a certifikace ale systém plně využívá optimalizované paměti 1 CPU workeru.
