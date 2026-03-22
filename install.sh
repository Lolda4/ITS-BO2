#!/bin/bash
# =============================================================================
# ITS-BO – Master Install Script
# Spusti jednou na serveru:  bash install.sh [SERVER_IP]
#
# Nainstaluje:
#   1. Python backend  (FastAPI, uvicorn) → systemd itsbo-backend.service
#   2. Next.js frontend                   → systemd itsbo-frontend.service
#   3. UFW firewall pravidla (porty 3000, 8000, 4500-5200/udp)
#   4. Systémové UDP buffery pro 25 Mbps příjem bez ztrát
#
# Po instalaci:
#   Backend:  http://<SERVER_IP>:8000
#   Frontend: http://<SERVER_IP>:3000
# =============================================================================
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_DIR/its-bo-backend"
FRONTEND_DIR="$REPO_DIR/its-bo-frontend"
SERVER_IP="${1:-$(hostname -I | awk '{print $1}')}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║          ITS-BO Test Platform – instalace                ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "  Repo dir:  $REPO_DIR"
echo "  Server IP: $SERVER_IP"
echo ""

# ── 0. Kontrola OS ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERR] python3 nenalezen. Nainstaluj: sudo apt install python3 python3-pip"
    exit 1
fi

# Node.js – pokud chybí, stáhni přes nvm nebo apt
if ! command -v node &>/dev/null; then
    echo "[1/?] Node.js nenalezen – instaluji přes NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# ── 1. Systémové UDP buffery ─────────────────────────────────────────────────
echo "[1/6] Konfigurace systémových UDP bufferů..."
sudo sysctl -w net.core.rmem_max=8388608
sudo sysctl -w net.core.rmem_default=4194304

SYSCTL_FILE="/etc/sysctl.d/99-itsbo.conf"
if ! grep -q "itsbo" "$SYSCTL_FILE" 2>/dev/null; then
    echo "net.core.rmem_max=8388608" | sudo tee "$SYSCTL_FILE"
    echo "net.core.rmem_default=4194304" | sudo tee -a "$SYSCTL_FILE"
    echo "  → $SYSCTL_FILE vytvořen"
fi

# ── 2. Backend Python závislosti ─────────────────────────────────────────────
echo "[2/6] Instalace Python závislostí (backend)..."
pip3 install -r "$BACKEND_DIR/requirements.txt" --break-system-packages 2>/dev/null || \
    pip3 install -r "$BACKEND_DIR/requirements.txt"

mkdir -p "$BACKEND_DIR/results" "$BACKEND_DIR/logs"

echo "  → FastAPI: $(python3 -c 'import fastapi; print(fastapi.__version__)')"
echo "  → Uvicorn: OK"

# ── 3. Frontend (Next.js build) ──────────────────────────────────────────────
echo "[3/6] Instalace npm závislostí a build frontendu..."
cd "$FRONTEND_DIR"

# Zapíše .env.production s IP serveru
cat > "$FRONTEND_DIR/.env.production" << ENVEOF
NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000
ENVEOF
echo "  → .env.production: NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000"

npm install --silent
npm run build
echo "  → Next.js build OK"
cd "$REPO_DIR"

# ── 4. Systemd – backend ─────────────────────────────────────────────────────
echo "[4/6] Registrace systemd služeb..."

UVICORN_BIN="$(which uvicorn)"

sudo tee /etc/systemd/system/itsbo-backend.service > /dev/null << EOF
[Unit]
Description=ITS-BO Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${BACKEND_DIR}
ExecStart=${UVICORN_BIN} main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment=ITSBO_RESULTS_DIR=${BACKEND_DIR}/results
Environment=ITSBO_LOGS_DIR=${BACKEND_DIR}/logs

[Install]
WantedBy=multi-user.target
EOF
echo "  → itsbo-backend.service"

# ── 5. Systemd – frontend ────────────────────────────────────────────────────
NODE_BIN="$(which node)"
NPM_BIN="$(which npm)"

sudo tee /etc/systemd/system/itsbo-frontend.service > /dev/null << EOF
[Unit]
Description=ITS-BO Frontend (Next.js)
After=network.target itsbo-backend.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${FRONTEND_DIR}
ExecStart=${NPM_BIN} start -- -p 3000
Restart=always
RestartSec=3
Environment=NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF
echo "  → itsbo-frontend.service"

sudo systemctl daemon-reload
sudo systemctl enable --now itsbo-backend itsbo-frontend
echo "  → Obě služby spuštěny a nastaveny na autostart"

# ── 6. Firewall ──────────────────────────────────────────────────────────────
echo "[6/6] Konfigurace UFW firewallu..."
if command -v ufw &>/dev/null; then
    sudo ufw allow 8000/tcp    comment "ITS-BO Backend"
    sudo ufw allow 3000/tcp    comment "ITS-BO Frontend"
    sudo ufw allow 4500:4599/udp comment "ITS-BO Control ports"
    sudo ufw allow 5100:5200/udp comment "ITS-BO Burst+Baseline ports"
    echo "  → Pravidla přidána"
else
    echo "  [WARN] UFW není nainstalován – otevři porty manuálně:"
    echo "         3000/tcp, 8000/tcp, 4500-4599/udp, 5100-5200/udp"
fi

# ── Shrnutí ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Instalace dokončena!                                    ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "  Frontend:  http://${SERVER_IP}:3000"
echo "  Backend:   http://${SERVER_IP}:8000/docs"
echo ""
echo "  Stav služeb:"
echo "    sudo systemctl status itsbo-backend"
echo "    sudo systemctl status itsbo-frontend"
echo ""
echo "  Logy:"
echo "    sudo journalctl -u itsbo-backend -f"
echo "    sudo journalctl -u itsbo-frontend -f"
echo "╚══════════════════════════════════════════════════════════╝"
