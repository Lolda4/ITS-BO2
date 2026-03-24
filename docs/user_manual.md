# ITS Test Platform: Průvodce Systémem
Tato příručka je sepsána pro koncové uživatele, výzkumníky a budoucí správce sítě, kteří potřebují porozumět tomu, jak funguje celý ekosystém **ITS-BO** (Back-Office Server) a **ITS-OBU** (On-Board Unit Android aplikace) – od základního zapojení až po řešení případných potíží v terénu.

---

## 1. Co tento systém vlastně dělá?
Systém slouží pro hromadný sběr telemetrických síťových dat při testování vozidel a komunikačních uzlů (tzv. zátěžové C-ITS testy).
Skládá se ze **dvou halvních prvků**, které spolu musí neustále mluvit:
1. **ITS-OBU (Aplikace v telefonu)** – Fyzicky se nachází v autě, měří sílu signálů, plní roli testovacího klienta a pod obrovskou zátěží střílí data do laboratoře.
2. **ITS-BO (Laboratorní Server)** – Univerzitní centrála sestrojená na systému Ubuntu Linux. Kontinuálně přijímá příchozí data z aut a live je vykresluje do elegantního černého webového dashboardu pro obsluhu laboratoře.

---

## 2. Architektura a Porty (Jak spolu mluví)
Aplikace z auta nepoužívá k posílání dat jen jeden kanál (aby se nezahltila dálnice), ale posílá je sofistikovaně po malých krabičkách (paketech) pomocí tzv. soketů:
- **Port 8000 (TCP)** – Hlavní Backend REST API. Slouží k ukládání finálních "JSON" výsledků po tom, co auto bezpečně dokončí test.
- **Port 4567 (UDP)** – *Control Loop*. Udržovací spojení, pomocí kterého server ví, jestli je k němu z mobilní aplikace právě teď aktivní session (test), nebo už skončil.
- **Port 5100 (UDP)** – *BurstReceiver*. Tudy doslova "tečou" ta obrovská objemová data tisíců měření za vteřinu, když je test v plném proudu.
- **Port 3000 (TCP)** – *Webový Frontend*. Sem se auto vůbec nepřipojuje. Sem chodí *člověk v laboratoři*, z jakéhokoliv prohlížeče, aby ty grafy z testu živě viděl.

> [!CAUTION] 
> Pokud je server fyzicky schovaný za obrovským "Fakultním routerem/Firewallem", musí mít tento router od pracovníků IT oddělení nastavený tzv. **Port Forwarding** (Propustnost). Rozhodně nenechte IT překládat porty z veřejného X na vnitřní Y! Telefon potřebuje plynule střílet na veřejnou IP laboratoře na port 8000 a ono to musí automaticky dopadnout na port 8000 serveru bez změny čísla (tzv. mapování 1:1 pro všechny 4 porty zmíněné výše).

---

## 3. Návod na zprovoznění Serveru (Ubuntu Linux)
Na čistě novém počítači (např. v IP adrese `192.168.0.161`):
1. Zapněte terminál stroje (nebo se na něj připojte přes SSH např. `ssh uzivatel@192.168.0.161`).
2. Stáhněte si celý projekt tímto jedním kódem, který zprovozní úplně vše:
   ```bash
   git clone https://github.com/Lolda4/ITS-BO2.git && cd ITS-BO2 && sudo bash install.sh 192.168.0.161
   ```
*(Pokud zahlásí "pip3 not found", doinstalujte jej příkazem `sudo apt update && sudo apt install -y python3-pip python3-venv` a spusťte install skript znovu.)*
3. A je to! Systém automaticky zaregistroval serverové služby v Linuxu a pustil API i Webový prohlížeč. Budou na něm puštěné vždy a navždy, i když počítač v laboratoři vytáhnete ze zásuvky a druhý den znovu zapnete.

---

## 4. Návod pro Terénní test (Mobil OBU)
Mobilní telefon musí mít staženou apk `ITS-OBU`. V dnešních moderních zařízeních, obzvláště u nadstaveb typu OxygenOS (OnePlus) či MIUI, dbejte na to, aby instalace nezkončila statusem `TEST_ONLY`, neboť v menu telefonu potom nenajdete spouštěcí ikonu!
*(Instalujte klasicky stiskem *Run* s korektním nastavením intent filtrů, nebo přes terminál ADB instalátorem naostro.)*

**Jakmile OBU spustíte a vyrazíte pod sluníčko:**
1. Stiskněte tlačítko nastavení.
2. Vložte **veřejnou IP adresu** sítě, ve které se laboratoř nachází (např. `147.32.102.209`).
3. Port nechte na `8000`. Nikdy nezadávejte "http://" – to si program dolepí sám. (Do API portu také logicky nevypisujte UDP porty).
4. Vraťte se zpět na domovskou obrazovku, cvakněte vytvořit test, zaškrtněte příslušné Use-casy (typy analýzy) a potvrďte spuštění! Notifikační lišta nahoře v telefonu bude test držet při životě po nezbytně nutnou dobu i při klidu.

---

## 5. Běžné potíže a Troubeshooting (FAQ)

**Q: Aplikace z auta hlásí "Server nenašel"!**
* KROK 1: Z jakéhokoliv notebooku či telefonu na *datech* (mimo fakultní síť) zkuste v `cmd`/terminálu zapsat `ping 147.32.102.209`. (ICMP mohl univerzitní firewall zablokovat, to je v pořádku, krok 2 ukáže víc).
* KROK 2: Dále napište `curl -v http://147.32.102.209:8000/docs` pro kontrolu API portu. Pokud vypíše "Connection Timed Out", s obrovskou jistotou za to nemůže chyba v kódu serveru, ale **nepropuštěný ochranný firewall sítě**. Zavolejte správce vaší sítě laboratoře.
* KROK 3: Pokud ale `HTTP 200 OK` proběhlo a API dokumentace se načetla normálně, je problém v samotném mobilním telefonu (zadali jste adresu s překlepem, s přidaným lomítkem, nebo bez internetového tarifu). 

**Q: Do laboratoře mi v dashboardu na portu 3000 nezobrazují grafy, i když auto hlásí 100% odesláno.**
* V laboratoři otevřete na serveru terminál a prohlédněte si hlavní logovací složku `nano ~/ITS-BO2/its-bo-backend/logs/itsbo.log`. 
* Na mobilu jděte do složky telefonu `/Android/data/cz.cvut.fel.itsobu/files/test_results/` – zde jsou k nalezení lokální offline JSON zálohy, pokud spojení spadlo! Json vždy ukazuje kompletní data.

**Q: Aplikace na mobilu mi spadne okamžitě po spuštění testu!**
* Android od verze 12 razantně omezil procesy na pozadí, tzv. `ForegroundServices`. Pro starší Androidy zkompilujte projekt ručně nebo v IDE smazáním `Context.startForegroundService` pojistek. Ujistěte se, že `PendingIntent.FLAG_IMMUTABLE` z notifikace nenechává prázdnou trasu na hlavní aktivitu aplikace. Systém ITS-OBU test-service by nyní již měl toto chování brát bezpečně v úvahu, jelikož cestu drží napevno přišroubovanou přes `setComponent`.
