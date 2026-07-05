# LiveTel Deployment Guide

> Step-by-step instructions for Oracle Cloud provisioning through live deployment.  
> Sections are filled in as each build phase completes.

**Last updated:** July 5, 2026

---

## Table of Contents

1. [Phase 1 — Oracle Cloud: Create Your VM](#phase-1--oracle-cloud-create-your-vm)
2. [Phase 2 — Connect via SSH](#phase-2--connect-via-ssh)
3. [Phase 3 — VM Hardening & Base Packages](#phase-3--vm-hardening--base-packages)
4. [Phase 4 — Install Ollama + Phi-3 Mini](#phase-4--install-ollama--phi-3-mini)
5. [Phase 5 — Deploy LiveTel Application](#phase-5--deploy-livetel-application)
6. [Phase 6 — Verify Live Demo](#phase-6--verify-live-demo)

---

## Phase 1 — Oracle Cloud: Create Your VM

_Coming in next step — follow along when README is approved and backend build begins._

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
8. **SSH keys:** Upload your public key (`~/.ssh/id_ed25519.pub`) or let Oracle generate one — **save the private key**
9. Click **Create**

Wait until **State** = `RUNNING`. Copy the **Public IP address** — you will need it for SSH and the live demo URL.

---

## Phase 2 — Connect via SSH

### From Windows (PowerShell)

```powershell
# If you uploaded your own key (default location):
ssh ubuntu@<YOUR_PUBLIC_IP>

# If Oracle generated the key:
ssh -i C:\path\to\your-private-key.key ubuntu@<YOUR_PUBLIC_IP>
```

**First connection:** type `yes` when prompted about host authenticity.

**If connection times out:**
- Confirm the instance is RUNNING
- Confirm Security List allows port 22 from `0.0.0.0/0`
- Confirm the instance has a **Public IP** (not just private)

---

## Phase 3 — VM Hardening & Base Packages

_Run these commands on the VM after your first SSH login. Full commands will be confirmed when we deploy._

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ufw fail2ban git curl nginx python3-pip python3-venv
# Node.js 20 — installed when we deploy the frontend
```

---

## Phase 4 — Install Ollama + Phi-3 Mini

_Detailed commands added when backend AI integration is complete._

---

## Phase 5 — Deploy LiveTel Application

_Git clone, backend venv, frontend build, systemd, Nginx — added after application code is ready._

---

## Phase 6 — Verify Live Demo

_Checklist added before go-live._

---

*This document grows with the project. Each completed build phase adds verified, copy-paste commands.*
