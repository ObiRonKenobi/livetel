import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import LiveTelLogo from './LiveTelLogo'

const METRICS_URL = '/api/metrics'
const ALERTS_URL = '/api/alerts'
const ALERT_STATS_URL = '/api/alerts/stats'
const CDRS_URL = '/api/cdrs'
const HISTORY_LIMIT = 60
const READ_KEY = 'livetel-read-alert-ids'
const ALERT_WINDOW_MS = 24 * 60 * 60 * 1000

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'cdr', label: 'CDR Stream' },
]

const SEVERITY_STYLES = {
  critical: { border: 'border-l-neonRed', badge: 'bg-neonRed text-white', text: 'text-neonRed', glow: 'shadow-[0_0_20px_rgba(255,7,58,0.2)]' },
  warning: { border: 'border-l-yellow-400', badge: 'bg-yellow-500/90 text-black', text: 'text-yellow-400', glow: 'shadow-[0_0_12px_rgba(250,204,21,0.15)]' },
  info: { border: 'border-l-vibrantBlue', badge: 'bg-vibrantBlue/30 text-vibrantBlue', text: 'text-vibrantBlue', glow: '' },
}

function loadReadIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem(READ_KEY) || '[]'))
  } catch {
    return new Set()
  }
}

function saveReadIds(set) {
  localStorage.setItem(READ_KEY, JSON.stringify([...set]))
}

function withinAlertWindow(isoString) {
  return Date.now() - new Date(isoString).getTime() < ALERT_WINDOW_MS
}

function filterRecentAlerts(list) {
  return list.filter((a) => withinAlertWindow(a.time) && !a.type.startsWith('AI_') && a.type !== 'AI_error')
}

const ALERT_TYPE_LABELS = {
  sip_trunk_unreachable: 'SIP Trunk Unreachable',
  toll_fraud: 'SIP Toll Fraud',
  sip_503_overload: 'SIP 503 — Service Unavailable',
  auth_failure: 'SIP Auth Failure',
  rtp_packet_loss: 'RTP Packet Loss',
  sip_latency_spike: 'SIP Latency Spike',
  codec_quality_drop: 'Codec Quality Drop',
  one_way_audio: 'One-Way Audio (RTP)',
  softphone_registration_failure: 'Softphone Registration Failure',
  sip_dns_timeout: 'SIP DNS / Timeout',
  carrier_outage: 'SIP Trunk Unreachable',
  trunk_exhaustion: 'SIP 503 — Service Unavailable',
  congestion: 'RTP Packet Loss',
  latency_spike: 'SIP Latency Spike',
  mos_degradation: 'Codec Quality Drop',
  dns_sip_failure: 'SIP DNS / Timeout',
  suspicious_international: 'SIP Toll Fraud',
}

function alertTypeLabel(type) {
  const base = type.startsWith('AI_') ? type.slice(3) : type
  return ALERT_TYPE_LABELS[base] || base.replace(/_/g, ' ')
}

function severityFor(alert) {
  return alert.severity || 'warning'
}

function severityStyle(sev) {
  return SEVERITY_STYLES[sev] || SEVERITY_STYLES.warning
}

function StatusDot({ status }) {
  const colors = { good: 'bg-green-500', warn: 'bg-yellow-400', bad: 'bg-neonRed animate-pulse-dot' }
  return <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${colors[status]}`} />
}

function mosStatus(mos) {
  if (mos >= 4.0) return 'good'
  if (mos >= 3.0) return 'warn'
  return 'bad'
}

function formatRelativeTime(isoString) {
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}

function formatTime(isoString) {
  return new Date(isoString).toLocaleTimeString()
}

function MetricChart({ title, dataKey, color, data, unit = '' }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4 shadow-lg">
      <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wide">{title}</h2>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis stroke="#888" tick={{ fontSize: 10 }} />
          <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }} labelStyle={{ color: '#00d4ff' }} />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
      {unit && <p className="text-xs text-gray-500 mt-1">{unit}</p>}
    </div>
  )
}

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75" onClick={onClose}>
      <div
        className={`bg-panel border border-border rounded-xl max-h-[90vh] overflow-hidden flex flex-col ${wide ? 'w-full max-w-4xl' : 'w-full max-w-2xl'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-vibrantBlue">{title}</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-white text-xl leading-none">&times;</button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  )
}

function AlertCard({ alert, prominent, unread, onOpenDetail, onDismiss }) {
  const sev = severityFor(alert)
  const st = severityStyle(sev)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpenDetail(alert)}
      onKeyDown={(e) => e.key === 'Enter' && onOpenDetail(alert)}
      className={`relative rounded-lg bg-darkBg border border-border cursor-pointer transition-opacity hover:opacity-95 ${prominent ? 'p-5' : 'p-3'} border-l-4 ${st.border} ${st.glow} ${unread ? 'ring-1 ring-white/10' : 'opacity-80'}`}
    >
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${st.badge}`}>
          {sev}
        </span>
        {unread && <span className="text-[10px] bg-white/10 text-white px-1.5 rounded">NEW</span>}
        <span className="text-xs text-gray-500">{formatRelativeTime(alert.time)}</span>
        <span className={`text-xs font-bold uppercase ${st.text}`}>{alertTypeLabel(alert.type)}</span>
      </div>
      <p className={`text-gray-200 leading-relaxed whitespace-pre-wrap ${prominent ? 'text-sm md:text-base' : 'text-sm line-clamp-4'}`}>
        {alert.details}
      </p>
      {prominent && (
        <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-border/50" onClick={(e) => e.stopPropagation()}>
          <button type="button" onClick={() => onDismiss(alert.id, 'resolved')} className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30">
            Mark resolved
          </button>
          <button type="button" onClick={() => onDismiss(alert.id, 'false_positive')} className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-gray-500/20 text-gray-400 hover:bg-gray-500/30">
            False positive
          </button>
        </div>
      )}
      {unread && (
        <p className="text-[10px] text-gray-500 mt-2">Click for full analysis & SIP evidence</p>
      )}
    </div>
  )
}

function AlertTicker({ alerts, unreadIds, onAlertClick }) {
  const recent = filterRecentAlerts(alerts)
  const unread = recent.filter((a) => !unreadIds.has(a.id))
  const items = (unread.length ? unread : recent).slice(0, 10)
  if (items.length === 0) return null
  const doubled = [...items, ...items]

  return (
    <div className="mb-4 bg-panel border border-neonRed/30 rounded-lg overflow-hidden cursor-pointer hover:border-neonRed/50" onClick={onAlertClick}>
      <div className="flex items-center gap-2 px-3 py-2 bg-neonRed/10 border-b border-neonRed/20">
        <span className="text-neonRed text-xs font-bold uppercase tracking-widest">Live Alerts</span>
        {unread.length > 0 && <span className="text-xs bg-neonRed text-white px-2 py-0.5 rounded-full font-bold">{unread.length} new</span>}
      </div>
      <div className="overflow-hidden py-2">
        <div className="alert-ticker-track gap-8 px-4">
          {doubled.map((alert, i) => {
            const st = severityStyle(severityFor(alert))
            return (
              <span key={`${alert.id}-${i}`} className="inline-flex items-center gap-3 shrink-0 text-sm">
                <span className={`font-bold uppercase text-xs px-1.5 rounded ${st.badge}`}>{severityFor(alert)}</span>
                <span className={`font-bold uppercase text-xs ${st.text}`}>{alertTypeLabel(alert.type)}</span>
                <span className="text-gray-400 max-w-sm truncate">{alert.details.slice(0, 70)}…</span>
                <span className="text-gray-600 text-xs">{formatRelativeTime(alert.time)}</span>
                <span className="text-border">|</span>
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function AlertStatsBar({ stats }) {
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      {[
        { label: 'Open', value: stats.open, color: 'text-neonRed', bg: 'bg-neonRed/10 border-neonRed/30' },
        { label: 'Resolved', value: stats.resolved, color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/30' },
        { label: 'False positives', value: stats.false_positive, color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/30' },
      ].map(({ label, value, color, bg }) => (
        <div key={label} className={`rounded-lg border px-4 py-3 ${bg}`}>
          <p className="text-[10px] text-gray-500 uppercase tracking-wide">Last 24h · {label}</p>
          <p className={`text-2xl font-bold tabular-nums ${color}`}>{value}</p>
        </div>
      ))}
    </div>
  )
}

const SIP_CODE_LABELS = {
  100: 'Trying',
  180: 'Ringing',
  200: 'OK',
  202: 'Accepted',
  401: 'Unauthorized',
  403: 'Forbidden',
  408: 'Timeout',
  503: 'Unavailable',
}

function CompactSipCodes({ errorCodes }) {
  const entries = Object.entries(errorCodes || {}).sort(([a], [b]) => Number(a) - Number(b))
  if (!entries.length) return null
  return (
    <div
      className="bg-panel border border-border rounded-lg px-4 py-3"
      title="Count of each SIP response code in signaling events from the last 60 seconds"
    >
      <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
        SIP response codes · last 60 seconds
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {entries.map(([code, count]) => {
          const n = Number(code)
          const label = SIP_CODE_LABELS[n] || 'Response'
          return (
            <span
              key={code}
              className={`text-xs font-mono px-2 py-1 rounded ${n >= 400 ? 'bg-neonRed/20 text-neonRed' : 'bg-vibrantBlue/10 text-vibrantBlue'}`}
              title={`${code} ${label}`}
            >
              {code} {label}: {count}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function CallFlowModal({ callId, onClose }) {
  const [flow, setFlow] = useState(null)
  useEffect(() => {
    fetch(`/api/calls/${callId}`).then((r) => r.json()).then(setFlow).catch(() => setFlow(null))
  }, [callId])

  return (
    <Modal title={`SIP Call Flow — ${callId}`} onClose={onClose} wide>
      {!flow && <p className="text-gray-500">Loading…</p>}
      {flow && (
        <div className="space-y-4">
          <p className="text-sm text-gray-400">{flow.events.length} signaling events · includes INVITE, BYE, REFER (transfer), voicemail legs</p>
          <div className="space-y-2">
            {flow.events.map((ev, i) => (
              <div key={ev.id || i} className="flex gap-3 items-start border-l-2 border-vibrantBlue/50 pl-3 py-2 font-mono text-xs">
                <span className="text-gray-500 w-16 shrink-0">{formatTime(ev.time)}</span>
                <span className="text-vibrantBlue w-16 shrink-0">Leg {ev.leg}</span>
                <span className="text-white w-20 shrink-0">{ev.sip_method}</span>
                <span className={`w-12 shrink-0 ${ev.sip_code >= 400 ? 'text-neonRed font-bold' : 'text-green-400'}`}>{ev.sip_code}</span>
                <span className="text-gray-400 uppercase w-16 shrink-0">{ev.direction}</span>
                <span className="text-gray-300 break-all">{ev.from_uri} → {ev.to_uri}</span>
                {ev.duration > 0 && <span className="text-gray-500 shrink-0">{ev.duration}s MOS {ev.mos}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}

function AlertDetailModal({ alert, onClose, onDismiss }) {
  const [ctx, setCtx] = useState(null)
  useEffect(() => {
    fetch(`/api/alerts/${alert.id}/context`).then((r) => r.json()).then(setCtx).catch(() => setCtx(null))
  }, [alert.id])

  const st = severityStyle(severityFor(alert))

  const dismiss = (status) => {
    onDismiss(alert.id, status)
    onClose()
  }

  return (
    <Modal title={alertTypeLabel(alert.type).toUpperCase()} onClose={onClose} wide>
      {!ctx && <p className="text-gray-500">Loading analysis…</p>}
      {ctx && (
        <div className="space-y-5">
          <div className={`p-4 rounded-lg border-l-4 ${st.border} bg-darkBg`}>
            <span className={`text-xs font-bold uppercase ${st.text}`}>{ctx.alert.severity} · {formatRelativeTime(ctx.alert.time)}</span>
            <p className="text-sm text-gray-200 mt-2 whitespace-pre-wrap">{ctx.alert.details}</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-vibrantBlue uppercase mb-2">Root Cause</h3>
            <p className="text-sm text-gray-300">{ctx.root_cause}</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-vibrantBlue uppercase mb-2">Mitigation</h3>
            <p className="text-sm text-gray-300 whitespace-pre-wrap">{ctx.mitigation}</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-vibrantBlue uppercase mb-2">Correlated SIP Events ({ctx.related_events.length})</h3>
            <div className="max-h-64 overflow-y-auto border border-border rounded-lg">
              <table className="w-full text-xs font-mono">
                <thead className="bg-darkBg text-gray-500 sticky top-0">
                  <tr>
                    <th className="px-2 py-2 text-left">Time</th>
                    <th className="px-2 py-2 text-left">Call ID</th>
                    <th className="px-2 py-2">Method</th>
                    <th className="px-2 py-2">Code</th>
                    <th className="px-2 py-2 text-left">From → To</th>
                  </tr>
                </thead>
                <tbody>
                  {ctx.related_events.map((r) => (
                    <tr key={r.id} className="border-t border-border/50">
                      <td className="px-2 py-1 text-gray-500">{formatTime(r.time)}</td>
                      <td className="px-2 py-1 text-vibrantBlue">{r.call_id.slice(0, 8)}…</td>
                      <td className="px-2 py-1 text-center">{r.sip_method}</td>
                      <td className={`px-2 py-1 text-center ${r.sip_code >= 400 ? 'text-neonRed' : ''}`}>{r.sip_code}</td>
                      <td className="px-2 py-1 text-gray-400 truncate max-w-xs">{r.from_uri} → {r.to_uri}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex flex-wrap gap-3 pt-2 border-t border-border">
            <button type="button" onClick={() => dismiss('resolved')} className="text-xs uppercase tracking-wide px-4 py-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 font-semibold">
              Mark resolved
            </button>
            <button type="button" onClick={() => dismiss('false_positive')} className="text-xs uppercase tracking-wide px-4 py-2 rounded-lg bg-gray-500/20 text-gray-400 hover:bg-gray-500/30 font-semibold">
              False positive — dismiss
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function CdrStreamTab({ search, setSearch, onSelectCall }) {
  const [cdrs, setCdrs] = useState([])
  const scrollRef = useRef(null)
  const pinnedRef = useRef(false)
  const searching = search.trim().length > 0

  useEffect(() => {
    pinnedRef.current = false
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [search])

  useEffect(() => {
    const fetchCdrs = async () => {
      try {
        const params = new URLSearchParams({ limit: searching ? '500' : '200' })
        if (searching) params.set('search', search.trim())
        const res = await fetch(`${CDRS_URL}?${params}`)
        const data = await res.json()
        if (searching || !pinnedRef.current) setCdrs(data)
      } catch { /* keep */ }
    }
    fetchCdrs()
    const id = setInterval(fetchCdrs, searching ? 5000 : 3000)
    return () => clearInterval(id)
  }, [search, searching])

  const onScroll = useCallback(() => {
    if (scrollRef.current && !searching) {
      pinnedRef.current = scrollRef.current.scrollTop > 80
    }
  }, [searching])

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <input
          type="search"
          placeholder="Search call ID, IP, number (+ optional), direction, SIP method/code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-darkBg border border-border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-vibrantBlue"
        />
        <span className="text-xs text-gray-500 shrink-0">
          {searching
            ? `${cdrs.length} matching event${cdrs.length === 1 ? '' : 's'}`
            : `${cdrs.length} events · scroll down to freeze · scroll to top for live`}
        </span>
      </div>
      <div className="bg-panel border border-border rounded-lg overflow-hidden">
        <div ref={scrollRef} onScroll={onScroll} className="overflow-x-auto max-h-[calc(100vh-280px)] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel border-b border-border text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-3">Time</th>
                <th className="px-3 py-3">Call ID</th>
                <th className="px-3 py-3">Dir</th>
                <th className="px-3 py-3">Method</th>
                <th className="px-3 py-3">From</th>
                <th className="px-3 py-3">To</th>
                <th className="px-3 py-3">Code</th>
                <th className="px-3 py-3">MOS</th>
              </tr>
            </thead>
            <tbody>
              {cdrs.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No events match.</td></tr>
              )}
              {cdrs.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => onSelectCall(row.call_id)}
                  className="border-b border-border/50 hover:bg-vibrantBlue/5 cursor-pointer font-mono text-xs"
                >
                  <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{formatTime(row.time)}</td>
                  <td className="px-3 py-2 text-vibrantBlue">{row.call_id.slice(0, 10)}…</td>
                  <td className={`px-3 py-2 uppercase ${row.direction === 'inbound' ? 'text-green-400' : 'text-orange-300'}`}>{row.direction}</td>
                  <td className="px-3 py-2">{row.sip_method}</td>
                  <td className="px-3 py-2 text-gray-300 max-w-[140px] truncate" title={row.from_uri}>{row.from_uri}</td>
                  <td className="px-3 py-2 text-gray-300 max-w-[140px] truncate" title={row.to_uri}>{row.to_uri}</td>
                  <td className={`px-3 py-2 ${row.sip_code >= 400 ? 'text-neonRed font-bold' : ''}`}>{row.sip_code}</td>
                  <td className="px-3 py-2">{row.mos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState('overview')
  const [metrics, setMetrics] = useState({ active_calls: 0, avg_latency: 0, avg_jitter: 0, avg_packet_loss: 0, avg_mos: 0, error_codes: {} })
  const [alerts, setAlerts] = useState([])
  const [alertStats, setAlertStats] = useState({ open: 0, false_positive: 0, resolved: 0, window_hours: 24 })
  const [cdrSearch, setCdrSearch] = useState('')
  const [history, setHistory] = useState([])
  const [readIds, setReadIds] = useState(() => loadReadIds())
  const [newAlertPulse, setNewAlertPulse] = useState(false)
  const [detailAlert, setDetailAlert] = useState(null)
  const [selectedCallId, setSelectedCallId] = useState(null)
  const prevUnread = useRef(0)

  const markRead = useCallback((id) => {
    setReadIds((prev) => {
      const next = new Set(prev)
      next.add(id)
      saveReadIds(next)
      return next
    })
  }, [])

  const markAllRead = useCallback(() => {
    setReadIds((prev) => {
      const next = new Set(prev)
      alerts.forEach((a) => next.add(a.id))
      saveReadIds(next)
      return next
    })
  }, [alerts])

  const dismissAlert = useCallback(async (id, status) => {
    try {
      await fetch(`/api/alerts/${id}/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      setAlerts((prev) => prev.filter((a) => a.id !== id))
      setAlertStats((prev) => ({
        ...prev,
        open: Math.max(0, prev.open - 1),
        false_positive: status === 'false_positive' ? prev.false_positive + 1 : prev.false_positive,
        resolved: status === 'resolved' ? prev.resolved + 1 : prev.resolved,
      }))
      markRead(id)
    } catch { /* keep */ }
  }, [markRead])

  const openAlertDetail = useCallback((alert) => {
    markRead(alert.id)
    setDetailAlert(alert)
  }, [markRead])

  const unreadCount = useMemo(() => alerts.filter((a) => !readIds.has(a.id)).length, [alerts, readIds])

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch(METRICS_URL)
        const data = await res.json()
        setMetrics(data)
        setHistory((prev) => [...prev, {
          time: new Date().toLocaleTimeString(),
          avg_latency: data.avg_latency,
          avg_jitter: data.avg_jitter,
          avg_packet_loss: data.avg_packet_loss,
          avg_mos: data.avg_mos,
          active_calls: data.active_calls,
        }].slice(-HISTORY_LIMIT))
      } catch { /* keep */ }
    }

    const fetchAlerts = async () => {
      try {
        const [alertsRes, statsRes] = await Promise.all([
          fetch(ALERTS_URL),
          fetch(ALERT_STATS_URL),
        ])
        const recent = filterRecentAlerts(await alertsRes.json())
        setAlerts(recent)
        setAlertStats(await statsRes.json())
      } catch { /* keep */ }
    }

    fetchMetrics()
    fetchAlerts()
    const a = setInterval(fetchMetrics, 3000)
    const b = setInterval(fetchAlerts, 10000)
    return () => { clearInterval(a); clearInterval(b) }
  }, [])

  useEffect(() => {
    setReadIds((prev) => {
      const openIds = new Set(alerts.map((a) => a.id))
      const next = new Set([...prev].filter((id) => openIds.has(id)))
      if (next.size !== prev.size) saveReadIds(next)
      return next
    })
  }, [alerts])

  useEffect(() => {
    if (unreadCount > prevUnread.current && prevUnread.current >= 0) {
      setNewAlertPulse(true)
      setTimeout(() => setNewAlertPulse(false), 2000)
    }
    prevUnread.current = unreadCount
  }, [unreadCount])

  const status = useMemo(() => ({
    latency: metrics.avg_latency > 200 ? 'bad' : metrics.avg_latency > 100 ? 'warn' : 'good',
    packetLoss: metrics.avg_packet_loss > 5 ? 'bad' : metrics.avg_packet_loss > 2 ? 'warn' : 'good',
    mos: mosStatus(metrics.avg_mos || 0),
    sipErrors: Object.entries(metrics.error_codes || {}).some(([c, n]) => Number(c) >= 400 && n > 5) ? 'bad' : 'good',
  }), [metrics])


  const avgMins = metrics.avg_call_duration_sec ? Math.round(metrics.avg_call_duration_sec / 60) : 0

  return (
    <div className="min-h-screen bg-darkBg p-4 md:p-6">
      <header className="flex flex-col md:flex-row md:justify-between md:items-end gap-4 mb-4 border-b border-border pb-4">
        <div className="flex items-stretch gap-3">
          <LiveTelLogo />
          <div className="flex flex-col justify-center">
            <h1 className="text-3xl md:text-4xl font-bold text-vibrantBlue tracking-tight leading-tight">LiveTel</h1>
            <p className="text-gray-400 text-sm mt-0.5 leading-snug">AI-Powered VoIP Operations</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Active Calls (live)</p>
          <p className="text-4xl font-bold text-neonRed tabular-nums">{metrics.active_calls ?? 0}</p>
          {avgMins > 0 && (
            <p className="text-[10px] text-gray-600 mt-1">avg call length ~{avgMins} min</p>
          )}
        </div>
      </header>

      <nav className="flex flex-wrap items-center gap-1 mb-4 border-b border-border">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`relative px-4 py-2.5 text-sm font-medium border-b-2 -mb-px ${
              tab === id ? 'border-vibrantBlue text-vibrantBlue' : 'border-transparent text-gray-500 hover:text-gray-300'
            } ${id === 'alerts' && newAlertPulse && tab !== 'alerts' ? 'badge-pulse rounded-t' : ''}`}
          >
            {label}
            {id === 'alerts' && unreadCount > 0 && (
              <span className="ml-2 inline-flex min-w-[1.25rem] h-5 px-1.5 text-xs font-bold rounded-full bg-neonRed text-white justify-center items-center">
                {unreadCount}
              </span>
            )}
          </button>
        ))}
        {tab === 'alerts' && unreadCount > 0 && (
          <button type="button" onClick={markAllRead} className="ml-auto text-xs text-vibrantBlue hover:underline mb-2">
            Mark all as read
          </button>
        )}
      </nav>

      {tab === 'overview' && (
        <>
          <AlertTicker alerts={alerts} unreadIds={readIds} onAlertClick={() => setTab('alerts')} />
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
            {[
              { label: 'Avg MOS', status: status.mos, value: (metrics.avg_mos || 0).toFixed(2) },
              { label: 'Latency', status: status.latency, value: `${metrics.avg_latency} ms` },
              { label: 'Jitter', status: status.latency, value: `${metrics.avg_jitter} ms` },
              { label: 'Packet Loss', status: status.packetLoss, value: `${metrics.avg_packet_loss}%` },
              { label: 'SIP Health', status: status.sipErrors, value: status.sipErrors === 'good' ? 'Normal' : 'Elevated' },
            ].map(({ label, status: s, value }) => (
              <div key={label} className="bg-panel border border-border rounded-lg px-3 py-2.5 flex items-center gap-2">
                <StatusDot status={s} />
                <div><p className="text-[10px] text-gray-500 uppercase">{label}</p><p className="text-sm font-semibold tabular-nums">{value}</p></div>
              </div>
            ))}
          </div>
          <div className="mb-4"><CompactSipCodes errorCodes={metrics.error_codes} /></div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <MetricChart title="Latency" dataKey="avg_latency" color="#00d4ff" data={history} unit="ms" />
            <MetricChart title="Jitter" dataKey="avg_jitter" color="#a78bfa" data={history} unit="ms" />
            <MetricChart title="Packet Loss" dataKey="avg_packet_loss" color="#ff073a" data={history} unit="%" />
            <MetricChart title="MOS Score" dataKey="avg_mos" color="#34d399" data={history} />
          </div>
        </>
      )}

      {tab === 'alerts' && (
        <>
          <AlertStatsBar stats={alertStats} />
          <div className="space-y-3 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
            {alerts.length === 0 && <p className="text-gray-500 text-center py-12">No open alerts in the last 24 hours.</p>}
            {alerts.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                prominent
                unread={!readIds.has(alert.id)}
                onOpenDetail={openAlertDetail}
                onDismiss={dismissAlert}
              />
            ))}
          </div>
        </>
      )}

      {tab === 'cdr' && (
        <CdrStreamTab search={cdrSearch} setSearch={setCdrSearch} onSelectCall={setSelectedCallId} />
      )}

      {detailAlert && <AlertDetailModal alert={detailAlert} onClose={() => setDetailAlert(null)} onDismiss={dismissAlert} />}
      {selectedCallId && <CallFlowModal callId={selectedCallId} onClose={() => setSelectedCallId(null)} />}

      <footer className="mt-8 text-center text-xs text-gray-600">Metrics & CDR 3s · SIP alerts 10s · 24h retention</footer>
    </div>
  )
}
