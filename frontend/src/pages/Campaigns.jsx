import { useState, useEffect } from 'react'
import { apiPost, apiGet, getUserPlan } from '../lib/api'

export default function Campaigns() {
  const plan = getUserPlan()
  const [campaigns, setCampaigns] = useState([])
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [stats, setStats] = useState({})    // { [id]: 'loading' | 'error:<msg>' | stats_obj }
  const [running, setRunning] = useState({}) // { [id]: bool }

  useEffect(() => { fetchCampaigns() }, [])

  async function fetchCampaigns() {
    try {
      const data = await apiGet('/campaigns')
      setCampaigns(data)
    } catch {}
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      await apiPost('/campaigns', { name: name.trim() })
      setName('')
      fetchCampaigns()
    } catch (err) {
      setCreateError(err.message)
    } finally {
      setCreating(false)
    }
  }

  async function handleRun(id) {
    setRunning(r => ({ ...r, [id]: true }))
    setStats(s => ({ ...s, [id]: 'loading' }))
    try {
      await apiPost(`/campaigns/${id}/run`)
      const s = await apiGet(`/campaigns/${id}/stats`)
      setStats(st => ({ ...st, [id]: s }))
      fetchCampaigns()
    } catch (err) {
      const msg = err.status === 422 ? 'No leads assigned to this campaign.' : err.message
      setStats(st => ({ ...st, [id]: 'error:' + msg }))
    } finally {
      setRunning(r => ({ ...r, [id]: false }))
    }
  }

  async function handleViewStats(id) {
    setStats(s => ({ ...s, [id]: 'loading' }))
    try {
      const s = await apiGet(`/campaigns/${id}/stats`)
      setStats(st => ({ ...st, [id]: s }))
    } catch (err) {
      const msg = err.status === 404 ? 'No stats yet — run the campaign first.' : err.message
      setStats(st => ({ ...st, [id]: 'error:' + msg }))
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Campaigns</h1>

      {plan === 'free' ? (
        <div style={{ ...card, background: '#fff8e1', border: '1px solid #ffe082' }}>
          <h3 style={{ marginTop: 0, color: '#e65100' }}>Campaigns — Pro Feature</h3>
          <p style={{ margin: 0, color: '#555' }}>Upgrade to Pro to run campaigns.</p>
        </div>
      ) : (
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>Create Campaign</h3>
          <form onSubmit={handleCreate} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>Campaign Name</label>
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                required
                placeholder="e.g. Q1 Outreach"
                style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: 4 }}
              />
            </div>
            <button
              type="submit"
              disabled={creating}
              style={{ padding: '0.45rem 1.25rem', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </form>
          {createError && <p style={{ color: '#c62828', marginTop: '0.5rem', fontSize: '0.9rem' }}>{createError}</p>}
        </div>
      )}

      <div style={{ ...card, marginTop: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Campaigns ({campaigns.length})</h3>
        {campaigns.length === 0 ? (
          <p style={{ color: '#888' }}>No campaigns yet. Create one above.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                {['Name', 'Status', 'Created', 'Actions'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {campaigns.map(c => (
                <CampaignRow
                  key={c.id}
                  campaign={c}
                  stat={stats[c.id]}
                  isRunning={!!running[c.id]}
                  onRun={() => handleRun(c.id)}
                  onStats={() => handleViewStats(c.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function CampaignRow({ campaign: c, stat, isRunning, onRun, onStats }) {
  return (
    <>
      <tr style={{ borderBottom: stat ? 'none' : '1px solid #eee' }}>
        <td style={td}>{c.name}</td>
        <td style={td}>
          <span style={{ ...badge, background: statusColor(c.status) }}>{c.status}</span>
        </td>
        <td style={td}>{new Date(c.created_at).toLocaleDateString()}</td>
        <td style={td}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={onRun} disabled={isRunning} style={smallBtn}>
              {isRunning ? 'Running…' : 'Run'}
            </button>
            <button onClick={onStats} style={smallBtn}>Stats</button>
          </div>
        </td>
      </tr>
      {stat && (
        <tr style={{ borderBottom: '1px solid #eee', background: '#f9f9f9' }}>
          <td colSpan={4} style={{ padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}>
            <StatsRow stat={stat} />
          </td>
        </tr>
      )}
    </>
  )
}

function StatsRow({ stat }) {
  if (stat === 'loading') return <span style={{ color: '#888' }}>Loading stats…</span>
  if (typeof stat === 'string' && stat.startsWith('error:')) {
    return <span style={{ color: '#c62828' }}>{stat.replace('error:', '')}</span>
  }
  return (
    <span>
      Leads: <b>{stat.total_leads}</b> &nbsp;|&nbsp;
      Sent: <b>{stat.sent_count}</b> &nbsp;|&nbsp;
      Opened: <b>{stat.opened_count}</b> &nbsp;|&nbsp;
      Replied: <b>{stat.replied_count}</b> &nbsp;|&nbsp;
      Failed: <b>{stat.failed_count}</b> &nbsp;|&nbsp;
      Status: <b>{stat.execution_status}</b>
    </span>
  )
}

function statusColor(s) {
  return { draft: '#888', active: '#2e7d32', paused: '#e65100', completed: '#1565c0', archived: '#555' }[s] || '#888'
}

const card = { background: '#fff', padding: '1.25rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
const th = { padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 600 }
const td = { padding: '0.5rem 0.75rem', verticalAlign: 'middle' }
const badge = { color: '#fff', padding: '0.2rem 0.6rem', borderRadius: 10, fontSize: '0.8rem' }
const smallBtn = { padding: '0.25rem 0.6rem', cursor: 'pointer', border: '1px solid #ccc', borderRadius: 4, background: '#fff', fontSize: '0.85rem' }
