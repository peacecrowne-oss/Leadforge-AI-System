import { useState, useEffect } from 'react'
import { apiGet } from '../lib/api'
import ReplyThread from '../components/ReplyThread'

export default function Inbox() {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState('loading') // loading | done | error
  const [expanded, setExpanded] = useState(null)  // lead_id of open thread

  useEffect(() => {
    apiGet('/inbox')
      .then(data => { setItems(data); setStatus('done') })
      .catch(() => setStatus('error'))
  }, [])

  function toggleThread(leadId) {
    setExpanded(id => id === leadId ? null : leadId)
  }

  if (status === 'loading') return <p style={meta}>Loading inbox…</p>
  if (status === 'error')   return <p style={{ ...meta, color: '#c62828' }}>Failed to load inbox.</p>
  if (items.length === 0)   return <p style={meta}>No conversations yet. Replies will appear here once leads respond.</p>

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Inbox</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {items.map(item => (
          <div key={item.lead_id} style={card}>
            <button
              onClick={() => toggleThread(item.lead_id)}
              style={rowBtn}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', minWidth: 0 }}>
                <span style={avatar}>{(item.full_name || '?')[0].toUpperCase()}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                    {item.full_name || 'Unknown Lead'}
                  </div>
                  <div style={preview}>
                    {item.latest_direction === 'inbound' ? '← ' : '→ '}
                    {item.latest_body.length > 80
                      ? item.latest_body.slice(0, 80) + '…'
                      : item.latest_body}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem', flexShrink: 0 }}>
                <span style={timestamp}>{new Date(item.latest_at).toLocaleString()}</span>
                <span style={badge}>{item.reply_count} {item.reply_count === 1 ? 'reply' : 'replies'}</span>
              </div>
            </button>

            {expanded === item.lead_id && (
              <div style={{ borderTop: '1px solid #eee', padding: '0.75rem 1rem' }}>
                <ReplyThread leadId={item.lead_id} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

const meta    = { fontSize: '0.9rem', color: '#888' }
const card    = { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', overflow: 'hidden' }
const rowBtn  = {
  width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  gap: '1rem', padding: '0.85rem 1rem', background: 'none', border: 'none',
  cursor: 'pointer', textAlign: 'left',
}
const avatar  = {
  width: 36, height: 36, borderRadius: '50%', background: '#1a1a2e', color: '#fff',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontWeight: 700, fontSize: '0.95rem', flexShrink: 0,
}
const preview   = { fontSize: '0.83rem', color: '#666', marginTop: '0.15rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 420 }
const timestamp = { fontSize: '0.75rem', color: '#999', whiteSpace: 'nowrap' }
const badge     = { fontSize: '0.72rem', background: '#e8f5e9', color: '#2e7d32', borderRadius: 10, padding: '0.1rem 0.45rem', fontWeight: 600 }
