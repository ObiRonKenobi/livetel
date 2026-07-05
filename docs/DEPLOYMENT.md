# LiveTel Deployment Guide

> Step-by-step instructions for Oracle Cloud provisioning through live deployment.

**Last updated:** July 5, 2026

---

## Table of Contents

1. [Phase 1 — Oracle Cloud: Create Your VM](#phase-1--oracle-cloud-create-your-vm)
2. [Phase 2 — Connect via SSH](#phase-2--connect-via-ssh)
3. [Phase 3 — VM Hardening & Base Packages](#phase-3--vm-hardening--base-packages)
4. [Phase 4 — Install Ollama + Phi-3 Mini](#phase-4--install-ollama--phi-3-mini)
5. [Phase 5 — Deploy LiveTel Application](#phase-5--deploy-livetel-application)
6. [Phase 6 — Verify Live Demo](#phase-6--verify-live-demo)
7. [Updating After Code Changes](#updating-after-code-changes)

---

## Phase 1 — Oracle Cloud: Create Your VM

### 1.1 Sign in to Oracle Cloud

1. Open [https://cloud.oracle.com](https://cloud.oracle.com)
2. Sign in with your Oracle Cloud account
3. Confirm you are in your **Home Region** (top-right). Ampere A1 availability varies by region; common choices: **US East (Ashburn)**, **US West (Phoenix)**, **Germany Central (Frankfurt)**

### 1.2 Create a compartment (optional but recommended)

1. Navigation menu → **Identity & Security** → **Compartments**
2. Click **Create Compartment**
3. Name: `livetel-demo` → **Create**

### 1.3 Create a Virtual Cloud Network (VCN)

1. Navigation menu → **Networking** → **Virtual Cloud Networks**
2. Click **Create VCN**
3. Select **VCN with Internet Connectivity** (wizard)
4. Name: `livetel-vcn`, Compartment: `livetel-demo` (or root)
5. IPv4 CIDR: `10.0.0.0/16` → **Next** → **Create**

The wizard creates a public subnet, Internet Gateway, and route table automatically.

### 1.4 Configure Security List (OCI firewall)

1. Open your new VCN → **Public Subnet** → **Security List**
2. Verify these **Ingress Rules** exist (add if missing):

| Source CIDR | Protocol | Destination Port | Description |
|-------------|----------|------------------|-------------|
| `0.0.0.0/0` | TCP | 22 | SSH |
| `0.0.0.0/0` | TCP | 80 | HTTP (demo) |

3. **Egress:** allow all outbound (default)

### 1.5 Create the compute instance

1. Navigation menu → **Compute** → **Instances** → **Create Instance**
2. **Name:** `livetel-demo`
3. **Compartment:** `livetel-demo`
4. **Image:** Ubuntu 22.04 or 24.04 (**ARM64**)
5. **Shape:** `VM.Standard.A1.Flex` — configure **4 OCPUs**, **24 GB RAM** (Free Tier max; use 2 OCPU / 12 GB if capacity is unavailable)
6. **Networking:** select `livetel-vcn` / public subnet
7. **Public IPv4 address:** Assign a public IPv4 address ✓
8. **SSH keys:** Upload your public key or let Oracle generate one — **save the private key**
9. Click **Create**

Wait until **State** = `RUNNING`. Copy the **Public IP address**.

**If Ampere capacity is unavailable:** try a different availability domain or region, or use 2 OCPU / 12 GB RAM.

---

## Phase 2 — Connect via SSH

### Generate an SSH key on Windows (if you don't have one)

```powershell
ssh-keygen -t ed25519 -C "livetel-oracle" -f $env:USERPROFILE\.ssh\id_ed25519_livetel
```

Upload the **public** key (`.pub` file contents) when creating the Oracle instance.

### Connect

```powershell
# Your own key:
ssh -i $env:USERPROFILE\.ssh\id_ed25519_livetel ubuntu@<YOUR_PUBLIC_IP>

# Oracle-generated key:
ssh -i C:\path\to\your-private-key.key ubuntu@<YOUR_PUBLIC_IP>
```

Type `yes` on first connection. If it times out, re-check Security List (port 22) and that the instance has a public IP.

---

## Phase 3 — VM Hardening & Base Packages

Run on the VM after first SSH login:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ufw fail2ban git curl nginx python3-pip python3-venv

# Firewall — only SSH and HTTP
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw enable

# Fail2Ban for SSH
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo systemctl enable fail2ban --now

# Node.js 20 (required for Vite frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v   # should show v20.x
```

---

## Phase 4 — Install Ollama + Phi-3 Mini

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

If the install script fails on ARM64:

```bash
sudo curl -L https://ollama.com/download/ollama-linux-arm64 -o /usr/bin/ollama
sudo chmod +x /usr/bin/ollama
```

Pull the model and verify:

```bash
sudo systemctl enable ollama --now
ollama pull phi3:mini
ollama run phi3:mini "Hello"   # quick test — Ctrl+D to exit
```

---

## Phase 5 — Deploy LiveTel Application

### 5.1 Clone the repository

```bash
cd ~
git clone https://github.com/ObiRonKenobi/livetel.git
cd livetel
```

### 5.2 Backend setup

```bash
cd ~/livetel/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Test locally (optional — Ctrl+C to stop):

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 5.3 Frontend build

```bash
cd ~/livetel/frontend
npm install
npm run build
```

Output: `frontend/dist/`

### 5.4 Systemd service (backend)

```bash
sudo cp ~/livetel/deploy/systemd/livetel-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable livetel-backend --now
sudo systemctl status livetel-backend
```

### 5.5 Nginx configuration

```bash
sudo cp ~/livetel/deploy/nginx/livetel.conf /etc/nginx/sites-available/livetel
sudo ln -sf /etc/nginx/sites-available/livetel /etc/nginx/sites-enabled/livetel
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 5.6 Confirm services

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
curl -s http://127.0.0.1/api/metrics | python3 -m json.tool
```

---

## Phase 6 — Verify Live Demo

Open in a browser: **`http://<YOUR_PUBLIC_IP>`**

Checklist:

- [ ] Dashboard loads with LiveTel header and "AI-Powered VoIP Operations" subtitle
- [ ] Active calls counter updates within a few seconds
- [ ] Latency / jitter / packet loss charts populate after ~3 minutes
- [ ] Within 5 minutes: injected anomaly alert appears (toll_fraud, carrier_outage, or congestion)
- [ ] Within 1–2 minutes after anomaly: AI alert appears (requires Ollama running)
- [ ] `http://<YOUR_PUBLIC_IP>/api/health` returns `"status": "ok"`

Share with your boss:

- **Live demo:** `http://<YOUR_PUBLIC_IP>`
- **Source code:** https://github.com/ObiRonKenobi/livetel

---

## Updating After Code Changes

On the VM after you push new code to GitHub:

```bash
cd ~/livetel
git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
sudo systemctl restart livetel-backend nginx
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `502 Bad Gateway` on `/api/` | `sudo systemctl status livetel-backend` — restart if failed |
| AI alerts show `AI_error` | Check Ollama: `systemctl status ollama`, `ollama list` |
| Charts empty | Wait 3+ minutes; confirm backend is generating CDRs |
| Can't SSH | Check OCI Security List port 22; confirm public IP |
| `npm run build` fails | Ensure Node 20+: `node -v` |
