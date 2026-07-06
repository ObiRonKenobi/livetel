import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const METRICS_URL = '/api/metrics'
const ALERTS_URL = '/api/alerts'
const CDRS_URL = '/api/cdrs'
const HISTORY_LIMIT = 60

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'cdr', label: 'CDR Stream' },
]

function StatusDot({ status }) {
  const colors = {
    good: 'bg-green-500',
    warn: 'bg-yellow-400',
    bad: 'bg-neonRed animate-pulse-dot',
  }
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
          <Tooltip
            contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
            labelStyle={{ color: '#00d4ff' }}
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
      {unit && <p className="text-xs text-gray-500 mt-1">{unit}</p>}
    </div>
  )
}

function AlertCard({ alert, prominent = false }) {
  const isAi = alert.type.startsWith('AI_')
  const isError = alert.type === 'AI_error'
  return (
    <div
      className={`p-3 rounded-lg bg-darkBg border ${
        prominent ? 'p-5' : 'p-3'
      } ${
        isAi
          ? 'border-neonRed/60 border-l-4 border-l-neonRed shadow-[0_0_20px_rgba(255,7,58,0.15)]'
          : isError
            ? 'border-yellow-500/60 border-l-4 border-l-yellow-500'
            : 'border-vibrantBlue/40 border-l-4 border-l-vibrantBlue'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {isAi && (
          <span className="text-[10px] font-bold uppercase tracking-widest bg-neonRed/20 text-neonRed px-2 py-0.5 rounded">
            AI Analysis
          </span>
        )}
        <span className="text-xs text-gray-500" title={new Date(alert.time).toLocaleString()}>
          {formatRelativeTime(alert.time)}
        </span>
        <span className={`text-xs font-bold uppercase tracking-wide ${isAi ? 'text-neonRed' : 'text-vibrantBlue'}`}>
          {alert.type.replace(/_/g, ' ')}
        </span>
      </div>
      <p className={`text-gray-200 leading-relaxed whitespace-pre-wrap ${prominent ? 'text-sm md:text-base' : 'text-sm'}`}>
        {alert.details}
      </p>
    </div>
  )
}

function AlertTicker({ alerts, onAlertClick }) {
  if (alerts.length === 0) return null

  const items = alerts.slice(0, 8)
  const doubled = [...items, ...items]

  return (
    <div
      className="mb-4 bg-panel border border-neonRed/30 rounded-lg overflow-hidden cursor-pointer hover:border-neonRed/50 transition-colors"
      onClick={onAlertClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onAlertClick()}
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-neonRed/10 border-b border-neonRed/20">
        <span className="text-neonRed text-xs font-bold uppercase tracking-widest shrink-0">Live Alerts</span>
        <span className="text-gray-500 text-xs">Click to open →</span>
      </div>
      <div className="overflow-hidden py-2">
        <div className="alert-ticker-track gap-8 px-4">
          {doubled.map((alert, i) => {
            const isAi = alert.type.startsWith('AI_')
            return (
              <span key={`${alert.time}-${i}`} className="inline-flex items-center gap-3 shrink-0 text-sm">
                <span className={`font-bold uppercase text-xs ${isAi ? 'text-neonRed' : 'text-vibrantBlue'}`}>
                  {alert.type.replace(/_/g, ' ')}
                </span>
                <span className="text-gray-400 max-w-md truncate">
                  {alert.details.slice(0, 80)}{alert.details.length > 80 ? '…' : ''}
                </span>
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

function CompactSipCodes({ errorCodes }) {
  const entries = Object.entries(errorCodes || {})
  if (entries.length === 0) return null

  return (
    <div className="bg-panel border border-border rounded-lg px-4 py-3 flex flex-wrap items-center gap-3">
      <span className="text-xs text-gray-500 uppercase tracking-wide shrink-0">SIP (60s)</span>
      {entries.map(([code, count]) => {
        const isError = Number(code) >= 400
        return (
          <span
            key={code}
            className={`text-xs font-mono px-2 py-1 rounded ${
              isError ? 'bg-neonRed/20 text-neonRed' : 'bg-vibrantBlue/10 text-vibrantBlue'
            }`}
          >
            {code}: {count}
          </span>
        )
      })}
    </div>
  )
}

function CdrStreamTab({ search, setSearch, cdrs }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <input
          type="search"
          placeholder="Filter by src, dst, or SIP code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-darkBg border border-border rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-vibrantBlue"
        />
        <span className="text-xs text-gray-500 shrink-0">{cdrs.length} records · updates every 3s</span>
      </div>
      <div className="bg-panel border border-border rounded-lg overflow-hidden">
        <div className="overflow-x-auto max-h-[calc(100vh-280px)] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel border-b border-border text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Src</th>
                <th className="px-4 py-3">Dst</th>
                <th className="px-4 py-3">Dur</th>
                <th className="px-4 py-3">MOS</th>
                <th className="px-4 py-3">Lat</th>
                <th className="px-4 py-3">Jitter</th>
                <th className="px-4 py-3">Loss</th>
                <th className="px-4 py-3">SIP</th>
              </tr>
            </thead>
            <tbody>
              {cdrs.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                    No CDRs match your filter.
                  </td>
                </tr>
              )}
              {cdrs.map((row, i) => (
                <tr
                  key={`${row.time}-${row.src}-${i}`}
                  className="border-b border-border/50 hover:bg-darkBg/80 font-mono text-xs"
                >
                  <td className="px-4 py-2 text-gray-400 whitespace-nowrap">{formatTime(row.time)}</td>
                  <td className="px-4 py-2 text-vibrantBlue">{row.src}</td>
                  <td className="px-4 py-2">{row.dst}</td>
                  <td className="px-4 py-2">{row.duration}s</td>
                  <td className={`px-4 py-2 ${row.mos < 3 ? 'text-neonRed' : row.mos >= 4 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {row.mos}
                  </td>
                  <td className="px-4 py-2">{row.latency}ms</td>
                  <td className="px-4 py-2">{row.jitter}ms</td>
                  <td className="px-4 py-2">{row.packet_loss}%</td>
                  <td className={`px-4 py-2 ${row.sip_code >= 400 ? 'text-neonRed font-bold' : ''}`}>
                    {row.sip_code}
                  </td>
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
  const [metrics, setMetrics] = useState({
    active_calls: 0,
    avg_latency: 0,
    avg_jitter: 0,
    avg_packet_loss: 0,
    avg_mos: 0,
    error_codes: {},
  })
  const [alerts, setAlerts] = useState([])
  const [cdrs, setCdrs] = useState([])
  const [cdrSearch, setCdrSearch] = useState('')
  const [history, setHistory] = useState([])
  const [newAlertPulse, setNewAlertPulse] = useState(false)
  const prevAlertCount = useRef(0)

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch(METRICS_URL)
        const data = await res.json()
        setMetrics(data)
        setHistory((prev) =>
          [...prev, {
            time: new Date().toLocaleTimeString(),
            avg_latency: data.avg_latency,
            avg_jitter: data.avg_jitter,
            avg_packet_loss: data.avg_packet_loss,
            avg_mos: data.avg_mos,
            active_calls: data.active_calls,
          }].slice(-HISTORY_LIMIT)
        )
      } catch { /* keep last */ }
    }

    const fetchAlerts = async () => {
      try {
        const res = await fetch(ALERTS_URL)
        const data = await res.json()
        if (data.length > prevAlertCount.current && prevAlertCount.current > 0) {
          setNewAlertPulse(true)
          setTimeout(() => setNewAlertPulse(false), 2000)
        }
        prevAlertCount.current = data.length
        setAlerts(data)
      } catch { /* keep last */ }
    }

    const fetchCdrs = async () => {
      try {
        const params = new URLSearchParams({ limit: '150' })
        if (cdrSearch.trim()) params.set('search', cdrSearch.trim())
        const res = await fetch(`${CDRS_URL}?${params}`)
        setCdrs(await res.json())
      } catch { /* keep last */ }
    }

    fetchMetrics()
    fetchAlerts()
    fetchCdrs()
    const metricsInterval = setInterval(fetchMetrics, 3000)
    const alertsInterval = setInterval(fetchAlerts, 10000)
    const cdrInterval = setInterval(fetchCdrs, 3000)
    return () => {
      clearInterval(metricsInterval)
      clearInterval(alertsInterval)
      clearInterval(cdrInterval)
    }
  }, [cdrSearch])

  const status = useMemo(() => ({
    latency: metrics.avg_latency > 200 ? 'bad' : metrics.avg_latency > 100 ? 'warn' : 'good',
    packetLoss: metrics.avg_packet_loss > 5 ? 'bad' : metrics.avg_packet_loss > 2 ? 'warn' : 'good',
    mos: mosStatus(metrics.avg_mos || 0),
    sipErrors: Object.entries(metrics.error_codes || {}).some(
      ([code, count]) => Number(code) >= 400 && count > 5
    ) ? 'bad' : 'good',
  }), [metrics])

  const aiAlertCount = alerts.filter((a) => a.type.startsWith('AI_')).length

  return (
    <div className="min-h-screen bg-darkBg p-4 md:p-6">
      <header className="flex flex-col md:flex-row md:justify-between md:items-end gap-4 mb-4 border-b border-border pb-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-vibrantBlue tracking-tight">LiveTel</h1>
          <p className="text-gray-400 text-sm mt-1">AI-Powered VoIP Operations</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Active Calls (60s)</p>
          <p className="text-4xl font-bold text-neonRed tabular-nums">{metrics.active_calls ?? 0}</p>
        </div>
      </header>

      {/* Tab bar with badge */}
      <nav className="flex gap-1 mb-4 border-b border-border">
        {TABS.map(({ id, label }) => {
          const isAlerts = id === 'alerts'
          const showBadge = isAlerts && alerts.length > 0
          return (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`relative px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                tab === id
                  ? 'border-vibrantBlue text-vibrantBlue'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              } ${isAlerts && newAlertPulse && tab !== 'alerts' ? 'badge-pulse rounded-t' : ''}`}
            >
              {label}
              {showBadge && (
                <span
                  className={`ml-2 inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 text-xs font-bold rounded-full ${
                    aiAlertCount > 0 ? 'bg-neonRed text-white' : 'bg-vibrantBlue/30 text-vibrantBlue'
                  }`}
                >
                  {alerts.length}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {tab === 'overview' && (
        <>
          <AlertTicker alerts={alerts} onAlertClick={() => setTab('alerts')} />

          {/* QoS summary */}
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
                <div className="min-w-0">
                  <p className="text-[10px] text-gray-500 uppercase truncate">{label}</p>
                  <p className="text-sm font-semibold tabular-nums">{value}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mb-4">
            <CompactSipCodes errorCodes={metrics.error_codes} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <MetricChart title="Latency" dataKey="avg_latency" color="#00d4ff" data={history} unit="ms" />
            <MetricChart title="Jitter" dataKey="avg_jitter" color="#a78bfa" data={history} unit="ms" />
            <MetricChart title="Packet Loss" dataKey="avg_packet_loss" color="#ff073a" data={history} unit="%" />
            <MetricChart title="MOS Score" dataKey="avg_mos" color="#34d399" data={history} />
          </div>
        </>
      )}

      {tab === 'alerts' && (
        <div className="space-y-3 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
          {alerts.length === 0 && (
            <p className="text-gray-500 text-center py-12">No alerts yet — anomalies inject every 5 minutes.</p>
          )}
          {alerts.map((alert, i) => (
            <div key={`${alert.time}-${i}`} className={i === 0 && newAlertPulse ? 'alert-flash rounded-lg' : ''}>
              <AlertCard alert={alert} prominent />
            </div>
          ))}
        </div>
      )}

      {tab === 'cdr' && (
        <CdrStreamTab search={cdrSearch} setSearch={setCdrSearch} cdrs={cdrs} />
      )}

      <footer className="mt-8 text-center text-xs text-gray-600">
        Metrics & CDR 3s · Alerts 10s · 24h retention
      </footer>
    </div>
  )
}
