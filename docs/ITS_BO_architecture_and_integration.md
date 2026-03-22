# ITS-BO (Backoffice) – Extrémně detailní technická dokumentace a analýza zdrojového kódu

Dokument tvoří obsáhlou kódovou mapu páteřního testovacího serveru (ITS-BO). Odkrývá, jak je vnitřní stavový engine s FastAPIm spojen s hardwarovými buffery z transportní sítě zařizující analýzu metrik. Cílem je detailně vysvětlit způsob fungování každé kritické subroutiny zpracovávající v reálném čase desetitisíce UDP datagramů vteřinově pro obhájení teze QoS (Quality of Service) specifikací na ETSI 5G V2X síti.

---

## 1. Softwarová Architektura Systému a Paralelizace
Systém v Python 3 se maximálně vyhýbá tradičním softwarovým bottleneckům. Není použit klasický blokovací WSGI přístroj ani masivní relační databáze generující diskové zámky I/O operace.
- Je vytvořen nad API **FastAPI s asynchronním ASGI serverem Uvicorn**. Veškerá komunikace s klientskými HTTP requests a zapisováním lokálních disků se provádí asynchronně (přes `await`).
- Transportní V2X mechanismy běží souběžně přes nativní Event Loop implementovaný v balíčku `asyncio`. Odmítá konvenční `threading` moduly s GIL ucpávačem za cenu vybudovaných Event-smyček. Reakční čas pro příjem UDP v asynchronním socketu limituje až k hranici reálné latence síťového hardwaru stroje.

---

## 2. API vrstva a Core Orchestrace (`main.py` & `core/`)

Srdce cloudových transakcí řeší propojení OBU klientských požadavků.

### 2.1 Životní cyklus backendu: `main.py`
Soubor ustavuje globální router a spouští server s Lifecycle hookem (`lifespan()`).
- Zaveze paměťové databáze `SessionCoordinator`, `PortAllocator` k izolování business logiky oddělené mimo aplikační HTTP bloky, aby byly staticky perzistující v hostu.
- Mapuje REST API Endpoints a typizuje HTTP Payload vstupy modelovým kontrolérem `pydantic.BaseModel` (mj. třída `SessionInitRequest`), který automaticky zahodí neplatné HTTP spojení např. bez parametru `uc_id` validním error kódem `HTTP 400`, chráníce infrastrukturu backendu proti pádu za běhu.
- Zavádí křížové originace přes injektovanou Middlewariu `CORSMiddleware`. Ta je podstatná pro front-end frameworkové Webové aplikace jako je i samotný řídicí React dashboard v kořenové lokální cestě, umožňující operátorské zkoušky na lab IP síti.
- Endpoint `/api/v1/session/status/{session_id}` vkládá novodobou Webovou komunikaci z asynchronního Event generatoru přes formát `sse_starlette.EventSourceResponse`. Zajišťuje, že namísto klientského polení frontendem se server rozhoduje otevřít s prohlížečem trvalou tcp linku v reálném čase jako rouru, pomocí které nasazuje každý 1 Hz živé updaty o rychlostech do řídicí vize. Využito k vykreslení webových dashboard chart line grafech průsaků paketů bez saturace API brán na serveru dotazováním. Zvyšuje efektivní propust.

### 2.2 `core/session_coordinator.py` a State Machine 
Obstarává celý život testovaných zkoušek na OBU skrze stavový strom reprezentací a propojování subsystému k minimalizaci ztracených stavů. Zásadně odmítá statické provázání v DB.
- Každá interakce nad definovaný `SessionState` blok je odpojena. Identifikátorem jediné session se tvoří zřetězení IDčka `uc_id`, časových kolíků a 4místné randomized soli do jedinečného klíče (př. `UC-A-20241031-152002-xkcd`) pro předejití kolizi. Z důvodu vkládání datových hashů a logických tras zátěže testu do stejného identifikátoru napříč gigabajty protokolů.
- `init_session()`: Metoda řešící první handshake vozidla s OBU. Sloučí vnitřní `parametry` profilu testu s defaulty dodanými přes ETSI normu, zajistí uvolnění transport ports na alokaci a zkompiluje strukturu zpět na OBU.
- `_monitor_timeout()` - Nejvýznamnější asynchronní zotavovač z výjimečné stavy sítě testu zkoušek. Běžící coroutine jako neoddělitelná součást Event loopu probouzející se 1vteřinově. Kontroluje poslední přijatý UDP datagram OBU klienta (`last_packet_time` updatovaný live metrikami socketů od vrstev transportu mimo core modul). Když se OBU dostaví zásahem do územé hlubky RF propasti signálu (nebo na Androidu crashne OBU aplikace), Cloudový timeout server na udřené vteřině 10 vyhodnotí stav, vyvolá fallback z otřesu `session.interrupt_reason = "no_packets_timeout"`, sám nasimuluje shození portů do `release()`, zajistí validní uklízení serveru od spoustou procesorově běžících UDP posluchačů a výsledek reportuje pod částečný fail stav, udrží server dostupný.

---

## 3. Výpočet QoS na Transportní Vrstvě (`transports/`)

Jedná se o hrubou sílu obstarávající měření ztrát napříč TCP/IP zásobníky pro certifikaci V2X podle standardu ETSI / 3GPP.

### 3.1 `burst_receiver.py` (Měření propustnosti a Jitteru do RFC)
Modul implementuje gigabitové readové toky simulovaného odesílacího C-ITS senzoru (UC-A a UC-B UpLinky z auta). Problémem standardního HTTP propustnění je absence Packet Loss / Time Sequence identifikací. Vývoj definoval naprosto oddělený `BurstReceiver` zřizující nehlídaný receiver socket formátu. 
- Změna UDP socketů pro L4 model v Pythonu pomocí volání kernel systémových voláních: `sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer_bytes)`. Nastaví buffer na nadstandardní 4 Megabyte zátěži k pokrytí mikrosekundo-krátkých výkyvu UDP toku přetečeného bufferem (nástroj nedovolí packet-loss z padnutého server OS schedulerů).
- Event-loop na příjmu asynchronně vytahuje hrubé bajtové svazky a obohatí je o Monotonic Time Arrival. 
- Obdržením přijatého burstu (včetně náročně simulovaných obřích frameů dat, které tvoří V2X), odpojuje prvních klíčových **18 Bytů proprietární binární zprávy**. Z důvodů nezávislosti Python `int.from_bytes(data[0:4], "big")` bezchybně zkonvertuje OBU byte seq hodnoty s nulovým string-parsing obsahem procesoru k naprosto okamžitě bezprostřední rychlosti na vteřinách. Data uloží interního List tuple modelu pro audit v evaluací bez databázového I/O pamatovákum. 
- `get_stats()`: Metoda postavená na matematice RFC 3550 pro **Packet Loss** (Vypočet missing ztrát z nejvyšího přečteného max - min Seq čísla oproti unique Countu zabrání desynchrozi padlých hlaviček balíčků). Počítá také **Jitter**, kdy vypočtená variance průměrné inter-arrival hodnoty určuje Jitter. Spolehlivost OBU měření závisí přesně do milisekund na matematické shodí.
- Systém doplňuje certifikaci čtením cache v `/proc/net/udp` z Inode jádra pro Socket Drops, vyvracuje zkázu lokálního sálové infrastruktury od 5G linky za oknem.

### 3.2 `udp_control_loop.py` (Teleoperace a E2E asymetrická latence bez NTP)
Architektura simulující řízení UC-C s kritickou R.5.4-004 garancí propustní spolehlivější hodnotám, než tradiční Pingy testovací sítě. OBU v Cloud serverech nesesynchronizovala nanosekundové časovače.
Backend definoval dvě masivní asynchronní tasks vlákén smýšlená napojením ke sdílenému I/O soketu k odpočítávání oboucestných ACK E2e latencí.
1. `_send_loop`: Každý stanovaný Interval Ns vypočítává odeslání 10 zpráv vteřinově pro obhájení v C-ITS simulaci řídícího auta. MCM JSON zprávy odřezává paddingem null 0x00 nulami na limitních 256 Bytů standardní zprávy, a vytvoří obalenou UDP síť daty obohacenou do interního `_sent_mcm` mapovaným záznamem lokálního odeslaného ITS-BO času zaslání paketu (z Monotonic clocků) se Sequence číslem řízení o pálícím OBU vozidla (Cesta T1).
2. `_recv_loop`: Přečte ACK reply v UDP, v kterých OBU potvrdilo dálkové navádění do formální zprávy na `serverControlPort`. Odebírá od `((data[5:13]))` zaslaných čas Processingových operací OBU procesoru (Cesta u OBU softwaru T3).
3. E2E výpočet je dokonale odveden bez ohledu nato, kde plujou po světě ntp pakety po síti takto z matematiky spojeného čtení na jednom serveru v jeden čas `recv_time_us (Příchozí T4 na BO) - send_time_us (Z mapy v T1) - obu_processing_us` jako nejčistčí matematický aproximovaný latencní výpočet Cesty OBU (Round trip), aproximované bezpečně vydělením / 2 na naprosto objektivní spolehlivost v End2End spravedlivé latence po 5G Rádio bloku k vozidlu v poli, bez ohledu kolikanásobně OBU zameškal z GC dropů.

## 4. Simulace Sítových Aplikačních zátěží C-ITS (`app_layer_simulator.py`)
Je naprosto zásadní demonstrovat datové kapacity, na kterých ITS specifikace selhávají.
- Plně obstarává vygenerování vládajících V2X model. Proti tradiční ASN.1 standardy tvořící UPER zprávy s tunou hlavičkových bitů (což sice zmenšuje velikosti, ale zatěžuje mobilní telefony nad dimenzování pro Měření kvality IP Site vrstvy na R.2.4 paramerech) – volí náš Cloud pro test pure JSON vygenerované sémanticky validní WG84 parametry, napadovaným byte streamem po velikosti.
- Přemísťuje `UC-B (See Through video)` do reálného světa video toků, obřím `build_video_gop` blokovačem prokládajícím `[frame_type:1B]` strukturu a imitací gigantického `I-Framu` definovaného nad 50 000 Byte velikostí. Tak velká síťová stopa projde UDP socketem s MTU `1472 Bytes` striktním rozfragmentováním, pálící kulometnou dávkou na mobilní 5G. Až na pozadí doplňována běžným propustným bufferem datovým tokem `P-Framu` (5 KB). Simulačně testově naprosto vyčerpávající simulací video kamer připínaných z autobusu za sebou k naprosto čistý propust. Zastíraje statické zobrazení předešlé.
