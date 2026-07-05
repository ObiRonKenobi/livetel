# LiveTel — Executive Summary

**Project:** AI-Powered VoIP Operations Demo  
**Author:** Engineering Team  
**Date:** July 5, 2026  
**Cost:** $0.00/month (Oracle Cloud Free Tier)

---

## Purpose

LiveTel demonstrates that **local AI can detect, diagnose, and explain VoIP network anomalies in real time** — without paid cloud APIs or proprietary tooling. Built as a leadership-ready prototype to encourage company-wide adoption of AI-assisted engineering.

---

## Engineering Pipeline (Idea → Live Demo)

| Step | Platform | Contribution |
|------|----------|--------------|
| 1. Requirements | **Google Gemini** | Translated business goals into technical architecture |
| 2. Roadmap | **DeepSeek** | Refined stack, timing, and step-by-step implementation plan |
| 3. Infrastructure | **Oracle Cloud (OCI)** | Free Tier Ampere ARM64 VM, VCN, security lists, SSH access |
| 4. Implementation | **Cursor IDE** | AI-assisted coding of backend, frontend, deployment configs |
| 5. Source control | **GitHub** | Public repository, version history, deployment source of truth |
| 6. Local AI | **Ollama + Phi-3 Mini** | On-VM incident analysis with zero per-query cost |

This pipeline shows AI as a **force multiplier across every phase** — not only in the finished product.

---

## Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| Backend | Python, FastAPI, SQLAlchemy | Fast REST API + background jobs on low-memory ARM VM |
| Database | SQLite | Zero-infra; UI polls same DB (always in sync) |
| Frontend | React, Vite, Tailwind, Recharts | Modern NOC-style dashboard with live SVG charts |
| AI | Ollama, Phi-3 Mini (3.8B Q4) | Fits 12 GB RAM; fully offline inference |
| Web / proxy | Nginx + rate limiting | Serves static frontend; proxies API |
| Process manager | systemd | Lightweight — no Docker RAM overhead |
| Security | UFW, fail2ban | SSH + HTTP only (raw IP demo, no TLS) |
| Hosting | Oracle Free Tier | ARM64 Ampere, $0/month |

---

## What the Demo Does

- Generates **3–8 synthetic call records per second** with realistic QoS metrics
- Injects **three anomaly types** every 5 minutes: toll fraud, carrier outage, network congestion
- Monitors aggregated metrics every **30 seconds**; calls local LLM when thresholds breach
- Displays a **live dashboard** polling every 3 seconds with 24-hour alert history
- Prunes data automatically every **15 minutes** (24-hour retention)

---

## Key Benefits Demonstrated

1. **Faster incident response** — AI surfaces root cause and mitigation instantly in the operator UI  
2. **Toll fraud visibility** — Unusual destination spikes detected within one monitoring window  
3. **Zero API costs** — Local LLM scales without per-call charges  
4. **24/7 unattended operation** — systemd services, auto-restart, automatic data pruning  

---

## Links

| Resource | URL |
|----------|-----|
| Live demo | `http://<VM-PUBLIC-IP>` _(update after deployment)_ |
| Source code | https://github.com/ObiRonKenobi/livetel |
| Deployment guide | https://github.com/ObiRonKenobi/livetel/blob/main/docs/DEPLOYMENT.md |

---

## Recommendation

This prototype proves that AI-enhanced operations are **immediately actionable** at zero marginal cost. The same pipeline — AI-assisted spec, roadmap, implementation, and local inference — can accelerate product teams across the organization. Recommended next steps: pilot on a staging VoIP environment, add HTTPS and auth for production, and evaluate larger local models as hardware allows.

---

*Print this page to PDF via browser (Ctrl+P → Save as PDF) or run: `pandoc EXECUTIVE_SUMMARY.md -o docs/executive-summary.pdf`*
