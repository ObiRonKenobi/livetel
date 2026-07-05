# LiveTel — AI-Powered VoIP Operations Demo

> **Project started:** July 5, 2026  
> **Status:** Application code complete — ready for Oracle VM deployment  
> **Live demo:** _Deploy using [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)_ → `http://<oracle-vm-ip>`  
> **Repository:** [github.com/ObiRonKenobi/livetel](https://github.com/ObiRonKenobi/livetel)

---

## What Is This?

**LiveTel** is a zero-cost, 24/7 live demonstration of AI-enhanced VoIP network operations. It simulates realistic call-detail record (CDR) traffic, injects network anomalies on a schedule, and uses a **local large language model** (Phi-3 Mini via Ollama) to diagnose incidents and suggest mitigation — all without paid cloud AI APIs.

Built to show leadership how AI-assisted engineering can move from idea to production-ready demo rapidly, at **$0/month** on Oracle Cloud Free Tier.

**Tagline:** *LiveTel — AI-Powered VoIP Operations*

---

## Engineering Pipeline

This project documents the full journey from concept to deployed demo:

| Phase | Tool / Platform | Role |
|-------|-----------------|------|
| Requirements & spec | Google Gemini | Translated business goals into technical architecture |
| Roadmap & refinement | DeepSeek | Optimized stack and step-by-step implementation plan |
| Oracle Cloud | OCI Free Tier (Ampere ARM64) | VM provisioning, networking, security |
| Implementation | Cursor IDE | AI-assisted coding, deployment configs, documentation |
| Source control | GitHub | Public repository and deployment source of truth |
| Local AI | Ollama + Phi-3 Mini | On-VM anomaly diagnosis (no external API costs) |

---

## Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | Python 3, FastAPI, SQLAlchemy | Fast REST API + background jobs on low-memory VM |
| Database | SQLite | Zero-infra persistence; UI polls same DB (always in sync) |
| Scheduler | APScheduler | CDR generation, anomaly injection, pruning, AI monitor |
| Frontend | React (Vite), Tailwind CSS, Recharts | Modern NOC-style dashboard with live charts |
| AI | Ollama, Phi-3 Mini (3.8B Q4) | Fits 12 GB RAM; fully offline inference |
| Web server | Nginx | Serves React build; reverse-proxies `/api/` |
| Process manager | systemd | Lightweight orchestration (no Docker overhead) |
| Security | UFW, fail2ban, Nginx rate limiting | SSH + HTTP only; no TLS (raw IP demo) |
| Hosting | Oracle Cloud Free Tier | ARM64 Ampere VM, $0/month |

---

## Key Capabilities

- **Synthetic VoIP traffic** — 3–8 CDRs/sec with realistic QoS metrics (MOS, latency, jitter, packet loss, SIP codes)
- **Scheduled anomaly injection** — toll fraud spikes, carrier outages, network congestion (every 5 minutes)
- **AI incident analysis** — local LLM explains root cause and mitigation (every 30 seconds when thresholds breach)
- **Live dashboard** — polls REST API every 3 seconds; 24h alert log with AI-highlighted entries
- **Automatic data pruning** — 24-hour retention, cleaned every 15 minutes

---

## Project Structure

```
livetel/
├── README.md
├── EXECUTIVE_SUMMARY.md      ← One-page report for leadership
├── docs/
│   └── DEPLOYMENT.md         ← Step-by-step Oracle VM + deploy guide
├── backend/                  ← FastAPI application
├── frontend/                 ← React dashboard (Vite + Tailwind + Recharts)
└── deploy/                   ← Nginx + systemd configs
```

---

## Quick Start (Local Backend Dev)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Frontend requires **Node.js 20+** (build on the Oracle VM — see deployment guide).

---

## Documentation

- [**Deployment guide**](docs/DEPLOYMENT.md) — Oracle VM provisioning through go-live
- [**Executive summary**](EXECUTIVE_SUMMARY.md) — one-page report for leadership

---

## License

MIT _(to be confirmed)_

---

*This README marks the official start of the LiveTel development timeline. Application code, deployment configs, and documentation will land in subsequent commits.*
