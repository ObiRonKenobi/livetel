#!/bin/bash
# LiveTel deploy — low-memory / template-AI mode (no Ollama)
set -euo pipefail

echo "==> Installing packages..."
sudo apt update
sudo apt install -y git curl nginx python3-pip python3-venv

echo "==> Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

echo "==> Cloning LiveTel..."
cd ~
if [ ! -d livetel ]; then
  git clone https://github.com/ObiRonKenobi/livetel.git
fi
cd livetel
git pull

echo "==> Backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "==> Frontend build..."
cd ../frontend
npm install
npm run build

echo "==> Systemd + Nginx..."
sudo cp ~/livetel/deploy/systemd/livetel-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable livetel-backend --now

sudo cp ~/livetel/deploy/nginx/livetel.conf /etc/nginx/sites-available/livetel
sudo ln -sf /etc/nginx/sites-available/livetel /etc/nginx/sites-enabled/livetel
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "==> Health check..."
sleep 3
curl -s http://127.0.0.1/api/health | python3 -m json.tool || true
curl -s http://127.0.0.1/api/metrics | python3 -m json.tool || true

echo ""
echo "Done. Open http://$(curl -s -H Metadata-Flavor:Google http://169.254.169.254/opc/v1/instance/metadata/publicIp) in your browser."
