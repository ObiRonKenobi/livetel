# LiveTel — Executive Summary

**Project:** AI-Powered VoIP Operations Demo  
**Author:** Engineering Team  
**Date:** July 5, 2026  
**Live demo:** http://129.213.54.237  
**Source:** https://github.com/ObiRonKenobi/livetel  
**Cost:** $0.00/month (Oracle Cloud Free Tier)

---

## Purpose

LiveTel demonstrates that **AI can accelerate every stage of building and operating a real-time VoIP NOC** — from requirements and architecture through implementation, deployment, and live incident analysis. The dashboard simulates a carrier-grade SIP environment (live concurrent calls, full call flows, softphone registration patterns) and surfaces **severity-ranked SIP alerts** with root cause, mitigation steps, and correlated CDR evidence.

This prototype was built to show leadership that AI-assisted engineering is not theoretical: it produced a **working 24/7 demo** at zero marginal API cost, and the same AI layer that helped write the code can run on-box to explain outages when hardware allows.

---

## AI Across the Full Pipeline

| Step | AI / Platform | How AI Added Value |
|------|---------------|-------------------|
| Requirements & vision | **Google Gemini** | Translated business goals into a concrete NOC feature set |
| Architecture & roadmap | **DeepSeek** | Refined stack choices, timing, and phased delivery plan |
| Implementation | **Cursor IDE** | AI pair-programming for FastAPI, React, nginx, systemd, and deploy automation |
| Infrastructure | **Oracle Cloud (OCI)** | Free-tier VM provisioned with AI-guided troubleshooting (capacity, firewall, nginx) |
| Source control | **GitHub** | Versioned artifact; repeatable deploys via `git pull` |
| **Runtime analysis (production path)** | **Ollama + Phi-3 Mini** | On-VM LLM generates natural-language incident write-ups from live SIP telemetry |
| **Runtime analysis (demo path)** | **Template engine** | Rule-based root cause + mitigation when RAM is constrained (see below) |

**Key message:** AI was a force multiplier in **how we built LiveTel** and is the designed upgrade path for **how it explains incidents at runtime**. The two are the same architecture — only the inference backend changes.

---

## Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| Backend | Python, FastAPI, SQLAlchemy | Fast REST API + scheduled jobs on a 1 GB micro VM |
| Database | SQLite | Zero extra infra; UI polls the same store (always in sync) |
| Frontend | React, Vite, Tailwind, Recharts | Modern NOC dashboard with live charts, CDR stream, alert workflow |
| AI (full mode) | Ollama, Phi-3 Mini (3.8B Q4) | Local inference; no per-query cloud fees |
| AI (demo mode) | Template analysis (`USE_TEMPLATE_AI=true`) | **Resource-saving choice** on 1 GB RAM — identical UI, deterministic expert text |
| Web / proxy | Nginx | Static frontend + API reverse proxy |
| Process manager | systemd | Lightweight; no Docker overhead on small VM |
| Security | UFW, fail2ban | SSH + HTTP (raw IP demo; TLS optional for production) |
| Hosting | Oracle Free Tier E2.1.Micro | Always-available shape; $0/month |

---

## What the Demo Does Today

- Maintains **~100–150 live concurrent SIP calls** with realistic URIs, directions, transfers, and voicemail legs
- Streams **CDR events** with call-status indicators (active vs completed) and alert correlation icons
- Injects **controlled anomaly bursts** every 5 minutes across **10 SIP/softphone anomaly types**
- Runs a **monitor service every 30 seconds** that aggregates telemetry and fires alerts when thresholds breach
- Serves a **tabbed dashboard** (Overview, Alerts, CDR Stream) with 24-hour retention and automatic pruning

---

## How the Code Detects Anomalies

Detection is a **two-stage pipeline**: telemetry aggregation, then rule-based classification. This is deliberately simple and auditable — the same aggregated metrics feed either the template engine or an LLM.

### Step 1 — Aggregate SIP telemetry (60-second window)

Every 30 seconds the monitor loads recent CDR rows and computes:

- Average **MOS**, **latency**, **jitter**, **RTP packet loss**
- **SIP error rate** (4xx/5xx responses)
- **401/403 rate** (auth / softphone registration stress)
- **408 rate** (timeouts / DNS-proxy issues)
- **503 rate** (service unavailable / session limits)
- **Premium-route ratio** (toll-fraud signature in destination URIs)

### Step 2 — Classify by severity

**Critical (red)** — immediate service impact:

| Anomaly | Trigger logic (simplified) |
|---------|---------------------------|
| SIP 503 — Service Unavailable | High 503 rate or combined error + 503 spike |
| SIP Trunk Unreachable | High SIP error rate without dominant 503 pattern |
| SIP Auth Failure | Elevated 401/403 rate |
| SIP Toll Fraud | Spike in calls to premium-route destinations |

**Warning (yellow)** — quality or softphone degradation:

| Anomaly | Trigger logic (simplified) |
|---------|---------------------------|
| SIP DNS / Timeout | Elevated 408 rate |
| One-Way Audio (RTP) | Packet loss > 8% |
| RTP Packet Loss | Packet loss > 5% or latency > 200 ms |
| SIP Latency Spike | Latency > 140 ms |
| Codec Quality Drop | MOS < 2.8 |
| Softphone Registration Failure | Moderate 401/403 elevation |

When a class fires, the system creates an alert with **severity**, **timestamp**, correlated CDR rows, **root cause**, and **mitigation** steps. Operators can mark alerts resolved or false positive from the UI.

### Step 3 — Explain the incident (AI-ready)

```
IF use_template_ai (1 GB demo VM):
    → template_analysis() writes expert NOC text from anomaly type + metrics
ELSE (Ollama available):
    → Phi-3 Mini prompt with latency, jitter, loss, error rate
    → Natural-language root cause + mitigation returned to UI
```

**The detection rules stay the same in both modes.** Only the narrative layer changes. Swapping `USE_TEMPLATE_AI=false` and running Ollama on a larger instance upgrades the demo to **true LLM-driven analysis** without rewriting the dashboard or SIP pipeline.

---

## Template Alerts vs Live AI — Strategic Framing

| | Template mode (current demo VM) | Full AI mode (recommended pilot) |
|--|--------------------------------|----------------------------------|
| **Why we use it** | 1 GB RAM cannot reliably host Ollama + app | 4–12 GB+ RAM; production-like inference |
| **Operator experience** | Same alerts, same severity colors, same CDR drill-down | Same UI — analysis text becomes LLM-generated |
| **Cost** | $0 | $0 marginal (local model) |
| **Upgrade path** | Set `USE_TEMPLATE_AI=false`, install Ollama, restart backend | Enable on staging trunk mirror |

The canned placeholder alerts are **not a limitation of the design** — they are a **deliberate resource-saving deployment choice** that proves the detection and UX loop works. AI replaces only the text generation step; the hard part (SIP telemetry, thresholding, correlation, workflow) is already built.

---

## Key Benefits Demonstrated

1. **AI-accelerated delivery** — Concept to live URL in days using AI for spec, plan, code, and deploy  
2. **Faster incident response** — Alerts bundle metrics, root cause, mitigation, and SIP evidence in one click  
3. **SIP + softphone coverage** — Ten anomaly types spanning trunks, auth, RTP, codecs, and web softphone registration  
4. **Zero API costs** — Local LLM path avoids per-incident cloud inference charges  
5. **24/7 unattended operation** — systemd services, auto-restart, 24-hour data pruning  
6. **Clear AI upgrade story** — Template mode today; flip one flag for Phi-3 (or larger) tomorrow  

---

## Links

| Resource | URL |
|----------|-----|
| **Live demo** | http://129.213.54.237 |
| **Source code** | https://github.com/ObiRonKenobi/livetel |
| **Deployment guide** | https://github.com/ObiRonKenobi/livetel/blob/main/docs/DEPLOYMENT.md |

---

## Recommendation

LiveTel shows that **AI belongs in every layer** of modern operations tooling: it helped define the product, write the code, deploy the infrastructure, and — when RAM permits — narrate incidents in operator language. The template engine on the current micro VM is a pragmatic stand-in, not a substitute for the architecture.

**Recommended next steps:**

1. Pilot on a **staging VoIP environment** with `USE_TEMPLATE_AI=false` and Ollama on 4+ GB RAM  
2. Mirror real SIP trunks and softphone registration logs into the CDR schema  
3. Add HTTPS, authentication, and role-based alert actions for production  
4. Evaluate larger local models (or hybrid cloud) as incident volume grows  

---

*Print to PDF: browser Ctrl+P → Save as PDF, or `pandoc EXECUTIVE_SUMMARY.md -o docs/executive-summary.pdf`*
