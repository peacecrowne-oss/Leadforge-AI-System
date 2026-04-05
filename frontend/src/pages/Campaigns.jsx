import { useState, useEffect } from 'react'
import { apiPost, apiGet, getUserPlan, getToken } from '../lib/api'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export default function Campaigns() {
  const plan = getUserPlan()
  const [campaigns, setCampaigns] = useState([])
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [stats, setStats] = useState({})    // { [id]: 'loading' | 'error:<msg>' | stats_obj }
  const [running, setRunning] = useState({}) // { [id]: bool }
  const [generatedMessages, setGeneratedMessages] = useState({})

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

  async function handleGenerateMessage(campaign) {
    const res = await fetch(`${API_BASE}/ai/generate-message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({
        business_name: campaign.name,
        industry: 'restaurant',
        pain_point: 'low online sales',
      }),
    })
    const data = await res.json()
    setGeneratedMessages(prev => ({ ...prev, [campaign.id]: data.message }))
  }

  async function handleSaveMessage(campaignId) {
    const message = generatedMessages[campaignId]
    const res = await fetch(`${API_BASE}/campaigns/${campaignId}/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ message }),
    })
    const data = await res.json()
    if (data.status === 'saved') {
      alert('Message saved!')
    } else {
      alert('Failed to save message')
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

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Create Campaign</h3>
        {plan === 'free' && (
          <p style={{ color: '#e65100', margin: '0 0 0.75rem', fontSize: '0.9rem' }}>
            Campaign automation requires a Pro plan.
          </p>
        )}
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
            disabled={creating || plan === 'free'}
            style={{ padding: '0.45rem 1.25rem', background: plan === 'free' ? '#aaa' : '#1a1a2e', color: '#fff', border: 'none', borderRadius: 4, cursor: plan === 'free' ? 'not-allowed' : 'pointer' }}
          >
            {creating ? 'Creating…' : 'Create'}
          </button>
        </form>
        {createError && <p style={{ color: '#c62828', marginTop: '0.5rem', fontSize: '0.9rem' }}>{createError}</p>}
      </div>

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
                  onGenerateMessage={() => handleGenerateMessage(c)}
                  generatedMessage={generatedMessages[c.id]}
                  onMessageChange={val => setGeneratedMessages(prev => ({ ...prev, [c.id]: val }))}
                  onSaveMessage={() => handleSaveMessage(c.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function CampaignRow({ campaign: c, stat, isRunning, onRun, onStats, onGenerateMessage, generatedMessage, onMessageChange, onSaveMessage }) {
  const [showMessage, setShowMessage] = useState(true)
  const [showStats, setShowStats]     = useState(true)

  const handleSendMessage = async () => {
    try {
      const res = await fetch(`${API_BASE}/messages/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          campaign_id: c.id,
          message: generatedMessage,
        }),
      })
      if (!res.ok) throw new Error('Failed to send message')
      alert('Message sent successfully')
    } catch (err) {
      console.error(err)
      alert('Failed to send message')
    }
  }

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
            <button onClick={onGenerateMessage} style={smallBtn}>Generate Message</button>
          </div>
        </td>
      </tr>
      {generatedMessage && showMessage && (
        <tr style={{ borderBottom: '1px solid #eee', background: '#fffde7' }}>
          <td colSpan={4} style={{ padding: '0.5rem 0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowMessage(false)} style={smallBtn}>✕</button>
            </div>
            <div style={{ marginTop: '10px' }}>
              <textarea
                value={generatedMessage}
                onChange={e => onMessageChange(e.target.value)}
                style={{ width: '100%', height: '120px', padding: '8px' }}
              />
              <button onClick={onSaveMessage} style={{ marginTop: '6px' }}>Save Message</button>
              <button onClick={handleSendMessage} style={{ marginTop: '6px', marginLeft: '0.5rem' }}>Send Message</button>
            </div>
          </td>
        </tr>
      )}
      {stat && showStats && (
        <tr style={{ borderBottom: '1px solid #eee', background: '#f9f9f9' }}>
          <td colSpan={4} style={{ padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowStats(false)} style={smallBtn}>✕</button>
            </div>
            <StatsRow stat={stat} />
          </td>
        </tr>
      )}
    </>
  )
}

function StatsRow({ stat }) {
  if (stat === 'loading') {
    return <div style={{ padding: '10px', color: '#888' }}>Loading stats...</div>
  }
  if (typeof stat === 'string' && stat.startsWith('error:')) {
    return <div style={{ padding: '10px', color: 'red' }}>{stat.replace('error:', '')}</div>
  }
  const s = stat
  const openRate = s.sent_count ? Math.round((s.opened_count / s.sent_count) * 100) : 0
  const replyRate = s.opened_count ? Math.round((s.replied_count / s.opened_count) * 100) : 0
  return (
    <div style={{ marginTop: '10px', padding: '12px', border: '1px solid #ddd', borderRadius: '8px', background: '#fafafa' }}>
      <strong>Campaign Stats</strong>
      <div>Leads: {s.total_leads}</div>
      <div>Sent: {s.sent_count}</div>
      <div>Opened: {s.opened_count} ({openRate}%)</div>
      <div>Replied: {s.replied_count} ({replyRate}%)</div>
      <div>Failed: {s.failed_count}</div>
      <div>Status: {s.execution_status}</div>
    </div>
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
