# ITS-BO – C-ITS Back Office Test Platform

Simulační platforma pro testování vysokodatové V2X komunikace mezi ITS Back Office (BO) a On-Board Unit (OBU). Součást diplomové práce na ČVUT FEL.

## Architektura

```
its-bo-backend/   Python 3.12 · FastAPI · uvicorn
                  Pluginy UC-A (SDSM), UC-B (See-Through), UC-C (Teleop), UC-D (OTA)
                  UDP burst příjem 100 Mbps · SSE live feed · Port 8000

its-bo-frontend/  Next.js 14 · React 18 · Tailwind CSS · Recharts
                  Dashboard, správa testů, výsledky · Port 3000
```

## Rychlý deploy na server (Linux)

### Požadavky
- Ubuntu 22.04 / Debian 12 (nebo kompatibilní)
- Python 3.10+
- Node.js 20+ (instalátor ho stáhne automaticky pokud chybí)
- sudo přístup

### Instalace – jeden příkaz

```bash
git clone https://github.com/Lolda4/ITS-BO2.git
cd ITS-BO2
bash install.sh <IP_SERVERU>
```

Příklad:
```bash
bash install.sh 192.168.1.100
```

Pokud vynecháš IP, skript ji detekuje automaticky (`hostname -I`).

### Co instalátor udělá

1. Nastaví systémové UDP buffery (16 MB) – nutné pro příjem 100 Mbps bez ztrát
2. Nainstaluje Python závislosti (`requirements.txt`)
3. Sestaví Next.js frontend (`npm install && npm run build`)
4. Zapíše `.env.production` s IP serveru pro API komunikaci
5. Zaregistruje dvě systemd služby (`itsbo-backend`, `itsbo-frontend`) s autorestartem
6. Otevře firewall porty (UFW)

### Po instalaci

| Služba | URL |
|--------|-----|
| Frontend dashboard | `http://<IP>:3000` |
| Backend REST API | `http://<IP>:8000` |
| API dokumentace | `http://<IP>:8000/docs` |

### Správa služeb

```bash
# Stav
sudo systemctl status itsbo-backend itsbo-frontend

# Logy (live)
sudo journalctl -u itsbo-backend -f
sudo journalctl -u itsbo-frontend -f

# Restart
sudo systemctl restart itsbo-backend
sudo systemctl restart itsbo-frontend
```

## Porty

| Port | Protokol | Účel |
|------|----------|------|
| 3000 | TCP | Next.js frontend |
| 8000 | TCP | FastAPI backend (REST + SSE) |
| 4500–4599 | UDP | Control loop per session |
| 5100–5199 | UDP | Burst příjem per session |
| 5200 | UDP | Baseline měření |

## Konfigurace (env vars)

Backend akceptuje tyto proměnné prostředí:

```bash
ITSBO_BIND_IP=0.0.0.0        # IP pro binding (default: 0.0.0.0)
ITSBO_API_PORT=8000           # REST API port
ITSBO_UDP_RECV_BUF=4194304   # UDP buffer v bajtech (4 MB default)
ITSBO_RESULTS_DIR=results     # Adresář pro JSON výsledky
ITSBO_LOGS_DIR=logs           # Adresář pro logy
```

Frontend:
```bash
NEXT_PUBLIC_API_URL=http://<IP>:8000  # URL backendu (nastaví install.sh)
```

## Vývoj (lokální spuštění)

```bash
# Backend
cd its-bo-backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (nový terminál)
cd its-bo-frontend
npm install
npm run dev
```

## Verze

- ITS-BO Backend: 3.0.0
- Kompatibilní s ITS-OBU v2.0.0 (Android, minSdk 29)
