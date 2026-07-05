import { useEffect, useMemo, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'

const METRICS_URL = '/api/metrics'
const ALERTS_URL = '/api/alerts'
const HISTORY_LIMIT = 60

function StatusDot({ status }) {
  const colors = {
    good: 'bg-green-500',
    warn: 'bg-yellow-400',
    bad: 'bg-neonRed animate-pulse-dot',
  }
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status]}`} />
}

function MetricChart({ title, dataKey, color, data, unit = '' }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4 shadow-lg">
      <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wide">{title}</h2>
      <ResponsiveContainer width="100%" height={200}>
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

function formatRelativeTime(isoString) {
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ago`
}

export default function App() {
  const [metrics, setMetrics] = useState({
    active_calls: 0,
    avg_latency: 0,
    avg_jitter: 0,
    avg_packet_loss: 0,
    error_codes: {},
  })
  const [alerts, setAlerts] = useState([])
  const [history, setHistory] = useState([])

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
            active_calls: data.active_calls,
          }].slice(-HISTORY_LIMIT)
        )
      } catch {
        /* keep last known values on poll failure */
      }
    }

    const fetchAlerts = async () => {
      try {
        const res = await fetch(ALERTS_URL)
        setAlerts(await res.json())
      } catch {
        /* keep last known alerts */
      }
    }

    fetchMetrics()
    fetchAlerts()
    const metricsInterval = setInterval(fetchMetrics, 3000)
    const alertsInterval = setInterval(fetchAlerts, 10000)
    return () => {
      clearInterval(metricsInterval)
      clearInterval(alertsInterval)
    }
  }, [])

  const status = useMemo(() => ({
    latency: metrics.avg_latency > 200 ? 'bad' : metrics.avg_latency > 100 ? 'warn' : 'good',
    packetLoss: metrics.avg_packet_loss > 5 ? 'bad' : metrics.avg_packet_loss > 2 ? 'warn' : 'good',
    sipErrors: Object.entries(metrics.error_codes || {}).some(
      ([code, count]) => Number(code) >= 400 && count > 5
    ) ? 'bad' : 'good',
  }), [metrics])

  const errorChartData = useMemo(
    () => Object.entries(metrics.error_codes || {}).map(([code, count]) => ({ code, count })),
    [metrics.error_codes]
  )

  return (
    <div className="min-h-screen bg-darkBg p-4 md:p-6">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:justify-between md:items-end gap-4 mb-6 border-b border-border pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold text-vibrantBlue tracking-tight">LiveTel</h1>
          <p className="text-gray-400 text-sm mt-1">AI-Powered VoIP Operations</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Active Calls (60s)</p>
          <p className="text-4xl font-bold text-neonRed tabular-nums transition-all duration-300">
            {metrics.active_calls ?? 0}
          </p>
        </div>
      </header>

      {/* Status strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        {[
          { label: 'Latency', status: status.latency, value: `${metrics.avg_latency} ms` },
          { label: 'Packet Loss', status: status.packetLoss, value: `${metrics.avg_packet_loss}%` },
          { label: 'SIP Health', status: status.sipErrors, value: status.sipErrors === 'good' ? 'Normal' : 'Elevated errors' },
        ].map(({ label, status: s, value }) => (
          <div key={label} className="bg-panel border border-border rounded-lg px-4 py-3 flex items-center gap-3">
            <StatusDot status={s} />
            <div>
              <p className="text-xs text-gray-500 uppercase">{label}</p>
              <p className="text-sm font-medium">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <MetricChart title="Latency" dataKey="avg_latency" color="#00d4ff" data={history} unit="milliseconds" />
        <MetricChart title="Jitter" dataKey="avg_jitter" color="#a78bfa" data={history} unit="milliseconds" />
        <MetricChart title="Packet Loss" dataKey="avg_packet_loss" color="#ff073a" data={history} unit="percent" />
        <MetricChart title="Active Calls" dataKey="active_calls" color="#34d399" data={history} />
      </div>

      {/* SIP error codes bar chart */}
      {errorChartData.length > 0 && (
        <div className="bg-panel border border-border rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wide">SIP Response Codes (60s)</h2>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={errorChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="code" stroke="#888" />
              <YAxis stroke="#888" allowDecimals={false} />
              <Tooltip contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }} />
              <Bar dataKey="count" fill="#00d4ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Alerts */}
      <div className="bg-panel border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-gray-300 mb-4 uppercase tracking-wide">Live Alerts Log (24h)</h2>
        <div className="h-72 overflow-y-auto space-y-2 pr-2">
          {alerts.length === 0 && (
            <p className="text-gray-500 text-sm">No alerts yet — anomalies inject every 5 minutes.</p>
          )}
          {alerts.map((alert, i) => {
            const isAi = alert.type.startsWith('AI_')
            const isError = alert.type === 'AI_error'
            return (
              <div
                key={`${alert.time}-${i}`}
                className={`p-3 rounded-lg bg-darkBg border border-border ${
                  isAi ? 'border-l-4 border-l-neonRed' : isError ? 'border-l-4 border-l-yellow-500' : 'border-l-4 border-l-vibrantBlue'
                }`}
              >
                <div className="flex flex-wrap items-baseline gap-2 mb-1">
                  <span className="text-xs text-gray-500" title={new Date(alert.time).toLocaleString()}>
                    {formatRelativeTime(alert.time)}
                  </span>
                  <span className={`text-xs font-bold uppercase tracking-wide ${isAi ? 'text-neonRed' : 'text-vibrantBlue'}`}>
                    {alert.type.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{alert.details}</p>
              </div>
            )
          })}
        </div>
      </div>

      <footer className="mt-8 text-center text-xs text-gray-600">
        Polling metrics every 3s · Alerts every 10s · Data retention 24h
      </footer>
    </div>
  )
}
