# LiveTel — Executive Summary

**Project:** AI-Powered VoIP Operations Demo  
**Author:** Ronald W. Sudol III  
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

## Synthetic SIP Traffic Framework

Because a live demo cannot depend on a real PBX or carrier trunks, LiveTel includes a **purpose-built traffic simulator** (`backend/services/generator.py`) that was designed and implemented with AI-assisted coding in Cursor. It is the engine that makes the NOC feel real — without external call sources or per-minute telecom costs.

### Architecture overview

The simulator runs as **scheduled background jobs** inside the FastAPI backend (APScheduler):

| Job | Interval | Module | Role |
|-----|----------|--------|------|
| `baseline_traffic` | Every **1 second** | `tick_live_calls()` | Advance live calls; emit SIP events; maintain 100–150 concurrent sessions |
| `inject_anomaly` | Every **5 minutes** | `generate_call_session()` | Inject a burst of degraded calls + create a matching alert |
| `monitor_and_alert` | Every **30 seconds** | `monitor.py` | Read generated CDRs; classify anomalies; write operator alerts |
| `prune_old_data` | Every **15 minutes** | `pruning.py` | Drop records older than 24 hours |

All synthetic events land in the **same SQLite database** the dashboard polls — there is no separate “demo mode” data path.

### Live concurrent call model

Each call is tracked in memory as a `LiveCall` object with a shared **16-character hex call ID** that ties every signaling event together:

1. **INVITE** → `100 Trying` → `180 Ringing` → `200 OK` (answered)
2. Optional **REFER** → `202 Accepted` → second-leg **INVITE** (call transfer, ~12% of normal calls)
3. Optional **voicemail leg** — REFER to `voicemail@<IP>` (~8% of normal calls)
4. **BYE** → `200 OK` when the call ends

Calls are held **live** until `end_at` — the dashboard “Active Calls” counter reflects calls that have received `200 OK` but not yet `BYE`, not merely events in a rolling window.

On startup the framework **seeds 110–130 in-progress calls** so the UI is immediately busy. Thereafter it starts 1–3 new calls per second when the pool drops below target, and tears down completed calls with a BYE.

### Realistic SIP addressing

The generator produces operator-credible URIs that mirror production CDR formats:

| Direction | From | To |
|-----------|------|-----|
| **Inbound** | `1234567890@<random-IP>` | `1234567890@livetel.net` |
| **Outbound** | `1234567890@livetel.net` | `+1…@<carrier-IP>` |

Each row also carries **direction**, **SIP method**, **response code**, **leg number**, and QoS fields (**MOS**, **latency**, **jitter**, **RTP packet loss**) — the same columns a real SBC or softphone platform would export.

### Controlled anomaly injection

Every five minutes `inject_anomaly()` randomly selects one of **10 anomaly types** and writes **8–15 complete call sessions** with signatures tuned to trigger detection:

- **SIP failures** — `401`, `403`, `408`, `503` on INVITE (auth, timeout, overload)
- **QoS degradation** — elevated latency, jitter, packet loss, collapsed MOS
- **Toll fraud** — destinations to `premium-route.xyz`
- **International patterns** — unusual `+44`, `+49`, etc. prefixes on outbound legs

An alert row is created in the same transaction, so the **Alerts tab**, **CDR stream icons**, and **correlated SIP evidence** modal always have data to show — even when no real network fault exists.

### Why this framework matters for the demo

1. **Zero external dependencies** — No SIP trunks, no softphone farm, no PCAP replay tools; one Python module drives the entire NOC  
2. **Believable operator UX** — Live call counts, scrolling CDRs, clickable call flows, active/completed indicators, and alert correlation behave like production tooling  
3. **Repeatable storytelling** — Anomalies fire on a schedule; leadership can watch the ticker, open an alert, and drill into SIP evidence in under a minute  
4. **Feeds the AI layer** — The monitor reads the same synthetic telemetry that a real deployment would produce; template or LLM analysis plugs in without schema changes  
5. **AI-accelerated build** — The state machine, URI rules, and scheduler wiring were implemented rapidly with Cursor; the framework itself is an example of AI shortening time-to-demo  

In a production pilot, this generator would be **replaced or fed by real CDR ingest** (syslog, SBC export, or softphone gateway). The dashboard, detection rules, and AI analysis path remain unchanged — only the data source swaps out.

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
2. **Synthetic traffic framework** — Self-contained SIP simulator drives 24/7 believable CDRs without real trunks  
3. **Faster incident response** — Alerts bundle metrics, root cause, mitigation, and SIP evidence in one click  
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
