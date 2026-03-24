import { useState, useEffect } from 'react'
import { apiGet, apiPost } from '../lib/api'

export default function ReplyThread({ leadId }) {
  const [replies, setReplies] = useState([])
  const [status, setStatus] = useState('loading') // loading | done | error
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState(null)

  useEffect(() => {
    apiGet(`/leads/${leadId}/replies`)
      .then(data => { setReplies(data); setStatus('done') })
      .catch(() => setStatus('error'))
  }, [leadId])

  async function handleSend(e) {
    e.preventDefault()
    setSending(true)
    setSendError(null)
    try {
      const reply = await apiPost(`/leads/${leadId}/replies`, { body: draft, direction: 'outbound' })
      setReplies(rs => [...rs, reply])
      setDraft('')
    } catch {
      setSendError('Failed to send reply.')
    } finally {
      setSending(false)
    }
  }

  if (status === 'loading') {
    return <p style={meta}>Loading…</p>
  }
  if (status === 'error') {
    return <p style={{ ...meta, color: '#c62828' }}>Failed to load replies.</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {replies.length === 0
        ? <p style={meta}>No replies yet.</p>
        : replies.map(r => (
            <div
              key={r.id}
              style={{ display: 'flex', justifyContent: r.direction === 'outbound' ? 'flex-end' : 'flex-start' }}
            >
              <div style={r.direction === 'outbound' ? outboundBubble : inboundBubble}>
                <p style={{ margin: 0, fontSize: '0.88rem' }}>{r.body}</p>
                {r.sender_email && (
                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', opacity: 0.65 }}>{r.sender_email}</p>
                )}
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', opacity: 0.55 }}>
                  {new Date(r.created_at).toLocaleString()}
                </p>
              </div>
            </div>
          ))
      }
      <form onSubmit={handleSend} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem' }}>
        <textarea
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder="Write a reply…"
          rows={2}
          style={{ flex: 1, padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4, resize: 'vertical', fontSize: '0.88rem', fontFamily: 'inherit' }}
        />
        <button type="submit" disabled={sending || !draft.trim()} style={sendBtn}>
          {sending ? '…' : 'Send'}
        </button>
      </form>
      {sendError && <p style={{ ...meta, color: '#c62828', marginTop: '0.2rem' }}>{sendError}</p>}
    </div>
  )
}

const meta = { margin: 0, fontSize: '0.85rem', color: '#888' }

const bubble = {
  maxWidth: '72%',
  padding: '0.5rem 0.75rem',
  borderRadius: 8,
  lineHeight: 1.4,
}

const inboundBubble = {
  ...bubble,
  background: '#f0f0f0',
  color: '#222',
}

const outboundBubble = {
  ...bubble,
  background: '#1a1a2e',
  color: '#fff',
}

const sendBtn = {
  padding: '0.4rem 0.9rem',
  background: '#1a1a2e',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: '0.88rem',
  alignSelf: 'flex-end',
}
