import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { healthCheck } from '../lib/api'

export default function Dashboard() {
  const [status, setStatus] = useState('checking')

  function check() {
    setStatus('checking')
    healthCheck()
      .then(() => setStatus('online'))
      .catch(() => setStatus('offline'))
  }

  useEffect(() => { check() }, [])

  const statusColor = { online: '#2e7d32', offline: '#c62828', checking: '#888' }[status]
  const statusLabel = { online: 'Online', offline: 'Offline', checking: 'Checking…' }[status]

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Dashboard</h1>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>System Status</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ ...badge, background: statusColor }}>{statusLabel}</span>
          <button onClick={check} style={ghostBtn}>Recheck</button>
        </div>
      </div>

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

const card = { background: '#fff', padding: '1.25rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
const badge = { color: '#fff', padding: '0.25rem 0.75rem', borderRadius: 12, fontSize: '0.9rem', fontWeight: 600 }
const ghostBtn = { padding: '0.3rem 0.75rem', cursor: 'pointer', borderRadius: 4, border: '1px solid #ccc', background: '#fff' }
const actionLink = { padding: '0.5rem 1.25rem', background: '#1a1a2e', color: '#fff', textDecoration: 'none', borderRadius: 4, fontWeight: 500 }
