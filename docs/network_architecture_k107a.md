# Síťová architektura K107A – Analýza a řešení přístupu

> Datum analýzy: 2026-03-24  
> Účel: Zprovoznění vzdáleného přístupu na ITS-BO VM z internetu pro terénní testování diplomové práce

---

## 1. Topologie sítě

```
Internet
    │
[ČVUT FW – gw.fd.cvut.cz]
    IP: 147.32.100.1
    Správce: Lukáš Svoboda
    │
[169.254.11.21]
    Neznámý L3 prvek (ČVUT switch/router)
    │
[TP-Link router]
    LAN IP:     192.168.0.1
    WAN IP:     147.32.103.236  ← veřejná IP laboratoře
    MAC:        00:31:92:b4:6e-2d (TP-Link Systems Inc.)
    Správce:    Martin Šrotýř
    │
    └── 192.168.0.0/24 (lokální LAN K107A)
              ├── 192.168.0.9    Amarisoft Callbox (eNodeB + EPC)
              ├── 192.168.0.109  Notebook (certilab)
              ├── 192.168.0.161  ITS-BO VM (Ubuntu 24.04)
              └── 192.168.0.x    ostatní zařízení v laboratoři
```

---

## 2. Síťová rozhraní notebooku (certilab)

| Adaptér | IP adresa | Síť | Poznámka |
|---|---|---|---|
| Intel Ethernet I219-V | 192.168.0.109 | 192.168.0.0/24 | Lokální LAN, přes TP-Link |
| Realtek USB GbE | 147.32.102.243 (DHCP, mění se) | ČVUT DHCP pool | Veřejná IP ale DHCP – nestabilní, pro terén se nepoužívá |
| Wi-Fi (AX201) | 192.168.0.192 | 192.168.0.0/24 | Lokální LAN |
| VMware VMnet8 | 192.168.188.1 | NAT | VMware interní |
| VMware VMnet1 | 192.168.11.1 | Host-only | VMware interní |

---

## 3. ITS-BO VM – síťová rozhraní

| Rozhraní | IP adresa | Síť | Poznámka |
|---|---|---|---|
| ens33 | 192.168.0.161/24 | 192.168.0.0/24 | Statická, Bridged VMnet0 |
| ens37 | 192.168.188.130/24 | 192.168.188.0/24 | DHCP, VMware NAT (VMnet8) |

**Statická route na VM pro Amarisoft UE síť:**
```
192.168.3.0/24 via 192.168.0.9
```

---

## 4. Porty potřebné pro ITS-BO platformu

| Port | Protokol | Služba |
|---|---|---|
| 22 | TCP | SSH (vzdálená správa) |
| 3000 | TCP | Next.js frontend |
| 8000 | TCP | FastAPI backend REST API |
| 4567 | UDP | UDP Control Loop (V2X řídicí smyčka) |
| 5100 | UDP | BurstReceiver (datový přenos OBU) |

---

## 5. Analýza dostupnosti z internetu

### Testování z externího PC (mimo ČVUT síť)

| IP | Port | Výsledek | Čas | Interpretace |
|---|---|---|---|---|
| 147.32.103.236 | 8000 | Connection refused | ~1s | FW aktivně blokuje (TCP Reset) – IP viditelná |
| 147.32.103.236 | 8000 | Timed out | ~7s | FW zahazuje pakety (DROP) – horší stav |
| 147.32.103.236 | — | ping timeout | — | ICMP blokovaný (normální) |
| 147.32.103.236 | — | ping timeout | — | ICMP blokovaný (normální) |

**Závěr:** Terénní přístup přes `147.32.103.236` je plně funkční – SSH i API odpovídají z externího PC. ✅

---

## 6. Tři VLAN sítě v K107A (dle Lukáše Svobody)

| VLAN | Síť | Správce | Poznámka |
|---|---|---|---|
| — | 192.168.0.0/24 | Martin Šrotýř | Lokální LAN laboratoře |
| 2607 | 192.168.107.0/24 | Lukáš Svoboda | Routovaná síť serverovna↔K107A |
| 2600 | veřejný internet | Lukáš Svoboda | Přímý přístup na internet |

---

## 7. Dvě cesty na internet z notebooku

### Cesta A – přes TP-Link (Intel Ethernet)
```
Notebook 192.168.0.109
    → TP-Link 192.168.0.1
    → 169.254.11.21
    → ČVUT FW 147.32.100.1
    → Internet
Veřejná IP: 147.32.103.236
Typ: pravděpodobně statická
```

### Cesta B – přes Realtek USB
```
Notebook Realtek USB
    → 169.254.11.21
    → ČVUT FW 147.32.100.1
    → Internet
Veřejná IP: 147.32.103.236
Typ: DHCP pool – nestabilní, může se změnit
```

---

## 8. Stav zprovoznění terénního přístupu – HOTOVO ✅

### Krok 1 – Martin (TP-Link router 192.168.0.1) ✅ HOTOVO
Port forwarding nastaven (ověřeno 2026-03-24):

| Veřejná IP | Port | Protokol | Cíl |
|---|---|---|---|
| 147.32.103.236 | 22 | TCP | 192.168.0.161:22 |
| 147.32.103.236 | 3000 | TCP | 192.168.0.161:3000 |
| 147.32.103.236 | 8000 | TCP | 192.168.0.161:8000 |
| 147.32.103.236 | 4567 | ALL | 192.168.0.161:4567 |
| 147.32.103.236 | 5100 | ALL | 192.168.0.161:5100 |

### Krok 2 – Lukáš (ČVUT FW) ✅ HOTOVO
Porty propuštěny – ověřeno testem z externího PC.

---

## 9. Alternativní řešení (dle návrhu Lukáše)

Zapojit notebook/VM přímo do VLAN 2600 (veřejný internet) druhým kabelem. VM by pak měla přímou veřejnou IP bez NATu.

**Nevýhody:**
- VM přímo exponovaná na internetu (bezpečnostní riziko)
- Nutná fyzická rekonfigurace portů na switchi
- Koordinace Martin + Lukáš

---

## 10. Aktuální stav přístupů (2026-03-24)

| Přístup | Příkaz | Stav |
|---|---|---|
| Lab SSH | `ssh itsbo@192.168.0.161` | ✅ funguje |
| Terén SSH | `ssh itsbo@147.32.103.236` | ✅ funguje |
| Terén API :8000 | `curl http://147.32.103.236:8000` | ✅ funguje |
| Terén Frontend :3000 | `http://147.32.103.236:3000` | ❓ neotestováno |
| Terén UDP :4567 | — | ❓ neotestováno |
| Terén UDP :5100 | — | ❓ neotestováno |

---

## 11. Windows port forwarding (dočasné řešení přes VMware NAT)

Nastaveno na Windows notebooku pro případ přístupu přes VMnet8 NAT:

```powershell
netsh interface portproxy add v4tov4 listenaddress=147.32.103.236 listenport=8000 connectaddress=192.168.188.130 connectport=8000
netsh interface portproxy add v4tov4 listenaddress=147.32.103.236 listenport=22 connectaddress=192.168.188.130 connectport=22
netsh interface portproxy add v4tov4 listenaddress=147.32.103.236 listenport=4567 connectaddress=192.168.188.130 connectport=4567
netsh interface portproxy add v4tov4 listenaddress=147.32.103.236 listenport=5100 connectaddress=192.168.188.130 connectport=5100
netsh interface portproxy add v4tov4 listenaddress=147.32.103.236 listenport=3000 connectaddress=192.168.188.130 connectport=3000
```

> **Poznámka:** Toto řešení nefunguje dokud ČVUT FW neotevře porty pro `147.32.103.236`.
