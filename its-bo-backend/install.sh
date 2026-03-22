#!/bin/bash
set -e

echo "=== ITS-BO Test Platform – instalace ==="

# 1. Systémové požadavky – KRITICKÉ pro UDP 25 Mbps příjem bez ztrát
echo "[1/5] Konfigurace systémových bufferů..."
sudo sysctl -w net.core.rmem_max=8388608
sudo sysctl -w net.core.rmem_default=4194304

# Persistentní konfigurace
if ! grep -q "itsbo" /etc/sysctl.d/99-itsbo.conf 2>/dev/null; then
    echo "net.core.rmem_max=8388608" | sudo tee /etc/sysctl.d/99-itsbo.conf
    echo "net.core.rmem_default=4194304" | sudo tee -a /etc/sysctl.d/99-itsbo.conf
    echo "  → Vytvořen /etc/sysctl.d/99-itsbo.conf"
else
    echo "  → /etc/sysctl.d/99-itsbo.conf již existuje"
fi

# 2. Python backend dependencies
echo "[2/5] Instalace Python závislostí..."
pip install -r requirements.txt --break-system-packages 2>/dev/null || \
    pip install -r requirements.txt

# 3. Adresáře
echo "[3/5] Vytváření adresářů..."
mkdir -p results logs

# 4. Ověření
echo "[4/5] Ověření instalace..."
python3 -c "import fastapi; print(f'  FastAPI {fastapi.__version__}')"
python3 -c "import uvicorn; print(f'  Uvicorn OK')"
python3 -c "from config import API_PORT; print(f'  Config OK (port {API_PORT})')"

# 5. Systemd služba (volitelné)
echo "[5/5] Systemd konfigurace..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cat > /tmp/itsbo-backend.service << EOF
[Unit]
Description=ITS-BO Backend
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${SCRIPT_DIR}
ExecStart=$(which uvicorn) main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment=ITSBO_RESULTS_DIR=${SCRIPT_DIR}/results
Environment=ITSBO_LOGS_DIR=${SCRIPT_DIR}/logs

[Install]
WantedBy=multi-user.target
EOF

echo "  → Systemd unit soubor vytvořen v /tmp/itsbo-backend.service"
echo "  → Pro instalaci: sudo cp /tmp/itsbo-backend.service /etc/systemd/system/"
echo "  → sudo systemctl daemon-reload && sudo systemctl enable --now itsbo-backend"

# Statická route (lab only – zakomentovat pro VPS)
echo ""
echo "=== Lab setup (volitelné) ==="
echo "  Statická route pro Callbox: sudo ip route add <UE_SUBNET>/24 via <CALLBOX_IP>"
echo ""
echo "=== VPS setup (volitelné) ==="
echo "  Firewall: sudo ufw allow 8000/tcp && sudo ufw allow 3000/tcp && sudo ufw allow 4500:5200/udp"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Hotovo. Spusť backend:"
echo "  cd ${SCRIPT_DIR}"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
echo "═══════════════════════════════════════════════════════════"
