import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, healthCheck } from '../lib/api'

export default function Dashboard() {
  const [healthStatus, setHealthStatus] = useState('checking')
  const [campaigns, setCampaigns] = useState(null)  // null = loading
  const [statsMap, setStatsMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  function checkHealth() {
    setHealthStatus('checking')
    healthCheck()
      .then(() => setHealthStatus('online'))
      .catch(() => setHealthStatus('offline'))
  }

  async function loadCampaigns() {
    setLoading(true)
    setError(null)
    try {
      const cList = await apiGet('/campaigns')
      setCampaigns(cList)
      const map = {}
      await Promise.all(cList.map(async c => {
        try {
          map[c.id] = await apiGet(`/campaigns/${c.id}/stats`)
        } catch (e) {
          if (e.status !== 404) console.warn(`stats ${c.id}:`, e.message)
          // 404 = campaign not run yet; skip silently
        }
      }))
      setStatsMap(map)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function refresh() {
    checkHealth()
    loadCampaigns()
  }

  useEffect(() => { refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived aggregates ─────────────────────────────────────────────────────
  const byStatus = {}
  if (campaigns) {
    for (const c of campaigns) {
      byStatus[c.status] = (byStatus[c.status] || 0) + 1
    }
  }

  const totals = { sent: 0, opened: 0, replied: 0 }
  for (const s of Object.values(statsMap)) {
    totals.sent    += s.sent_count    || 0
    totals.opened  += s.opened_count  || 0
    totals.replied += s.replied_count || 0
  }

  const healthColor = { online: '#2e7d32', offline: '#c62828', checking: '#888' }[healthStatus]
  const healthLabel = { online: 'Online', offline: 'Offline', checking: 'Checking…' }[healthStatus]
  const n = campaigns ? campaigns.length : null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Dashboard</h1>
        <button onClick={refresh} disabled={loading} style={ghostBtn}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {/* ── Metric cards ── */}
      <div style={metricsGrid}>
        <MetricCard label="Backend"           value={healthLabel}                accent={healthColor} />
        <MetricCard label="Total Campaigns"   value={n ?? '—'} />
        <MetricCard label="Completed"         value={n != null ? (byStatus.completed || 0) : '—'} />
        <MetricCard label="Draft"             value={n != null ? (byStatus.draft     || 0) : '—'} />
        <MetricCard label="Running"           value={n != null ? (byStatus.active    || 0) : '—'} />
        <MetricCard label="Emails Sent"       value={totals.sent} />
        <MetricCard label="Emails Opened"     value={totals.opened} />
        <MetricCard label="Replies"           value={totals.replied} />
      </div>

      {/* ── Error state ── */}
      {error && (
        <p style={{ color: '#c62828', marginTop: '1rem' }}>
          Failed to load campaigns: {error}
        </p>
      )}

      {/* ── Campaign summary ── */}
      {!error && (
        <div style={{ ...card, marginTop: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0 }}>Campaign Summary</h3>
            <Link to="/campaigns" style={smallLink}>Manage campaigns →</Link>
          </div>

          {loading ? (
            <p style={{ color: '#888', margin: 0 }}>Loading…</p>
          ) : campaigns && campaigns.length === 0 ? (
            <p style={{ color: '#888', margin: 0 }}>
              No campaigns yet.{' '}
              <Link to="/campaigns" style={{ color: '#1a1a2e' }}>Create your first campaign →</Link>
            </p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    {['Name', 'Status', 'Created', 'Sent', 'Opened', 'Replied'].map(h => (
                      <th key={h} style={th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(campaigns || []).map(c => {
                    const s = statsMap[c.id]
                    return (
                      <tr key={c.id} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={td}>{c.name}</td>
                        <td style={td}><StatusBadge status={c.status} /></td>
                        <td style={{ ...td, color: '#888', fontSize: '0.82rem' }}>
                          {new Date(c.created_at).toLocaleDateString()}
                        </td>
                        <td style={td}>{s ? s.sent_count    : '—'}</td>
                        <td style={td}>{s ? s.opened_count  : '—'}</td>
                        <td style={td}>{s ? s.replied_count : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Quick actions ── */}
      <div style={{ ...card, marginTop: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Quick Actions</h3>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <Link to="/leads" style={actionLink}>Search Leads</Link>
          <Link to="/campaigns" style={actionLink}>View Campaigns</Link>
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ label, value, accent }) {
  return (
    <div style={card}>
      <div style={{ fontSize: '0.75rem', color: '#888', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: accent || '#1a1a2e' }}>
        {value}
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const colors = {
    draft:     { bg: '#e3f2fd', text: '#1565c0' },
    active:    { bg: '#e8f5e9', text: '#2e7d32' },
    paused:    { bg: '#fff8e1', text: '#f57f17' },
    completed: { bg: '#f3e5f5', text: '#6a1b9a' },
    archived:  { bg: '#f5f5f5', text: '#616161' },
  }
  const c = colors[status] || colors.archived
  return (
    <span style={{ ...statusBadgeStyle, background: c.bg, color: c.text }}>{status}</span>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const card        = { background: '#fff', padding: '1.25rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
const metricsGrid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.75rem' }
const ghostBtn    = { padding: '0.3rem 0.75rem', cursor: 'pointer', borderRadius: 4, border: '1px solid #ccc', background: '#fff' }
const actionLink  = { padding: '0.5rem 1.25rem', background: '#1a1a2e', color: '#fff', textDecoration: 'none', borderRadius: 4, fontWeight: 500 }
const smallLink   = { fontSize: '0.85rem', color: '#1a1a2e', textDecoration: 'none' }
const statusBadgeStyle = { fontSize: '0.78rem', fontWeight: 600, padding: '0.15rem 0.5rem', borderRadius: 10 }
const th          = { padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 600 }
const td          = { padding: '0.5rem 0.75rem', verticalAlign: 'middle' }
