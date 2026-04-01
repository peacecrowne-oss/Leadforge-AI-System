import { useState, useEffect } from 'react'
import { apiGet } from '../lib/api'
import ReplyThread from '../components/ReplyThread'

// The job whose leads are checked for replies.
// Change this to any completed job_id to load a different import's conversations.
const JOB_ID = "063b0afb-cd3e-431f-94c6-0c188896cc27"

export default function Inbox() {
  const [threads, setThreads]   = useState([])
  const [status, setStatus]     = useState('loading') // loading | done | error
  const [expanded, setExpanded] = useState(null)       // lead_id of open thread

  useEffect(() => {
    async function loadThreads() {
      try {
        // Step 1: fetch all leads for the job.
        const { results: leads } = await apiGet(`/leads/jobs/${JOB_ID}/results`)

        // Step 2: fetch replies for every lead in parallel.
        // A failed per-lead call resolves to [] so one bad lead doesn't abort all.
        const replyLists = await Promise.all(
          leads.map(lead => apiGet(`/leads/${lead.id}/replies`).catch(() => []))
        )

        // Step 3: build thread objects — only for leads that have replies.
        const built = []
        for (let i = 0; i < leads.length; i++) {
          const replies = replyLists[i]
          if (!replies || replies.length === 0) continue

          // Sort replies newest-first to find the latest one.
          const sorted = [...replies].sort(
            (a, b) => b.created_at.localeCompare(a.created_at)
          )
          const latest = sorted[0]

          built.push({
            lead_id:          leads[i].id,
            name:             leads[i].full_name,
            latest_body:      latest.body,
            latest_direction: latest.direction,
            latest_at:        latest.created_at,
            reply_count:      replies.length,
          })
        }

        // Sort threads newest-first by their latest reply.
        built.sort((a, b) => b.latest_at.localeCompare(a.latest_at))

        setThreads(built)
        setStatus('done')
      } catch {
        setStatus('error')
      }
    }

    loadThreads()
  }, [])

  function toggleThread(leadId) {
    setExpanded(id => id === leadId ? null : leadId)
  }

  if (status === 'loading') return <p style={meta}>Loading inbox…</p>
  if (status === 'error')   return <p style={{ ...meta, color: '#c62828' }}>Failed to load inbox.</p>
  if (threads.length === 0) return <p style={meta}>No conversations yet. Replies will appear here once leads respond.</p>

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Inbox</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {threads.map(thread => (
          <div key={thread.lead_id} style={card}>
            <button
              onClick={() => toggleThread(thread.lead_id)}
              style={rowBtn}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', minWidth: 0 }}>
                <span style={avatar}>{(thread.name || '?')[0].toUpperCase()}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                    {thread.name || 'Unknown Lead'}
                  </div>
                  <div style={preview}>
                    {thread.latest_direction === 'inbound' ? '← ' : '→ '}
                    {thread.latest_body.length > 80
                      ? thread.latest_body.slice(0, 80) + '…'
                      : thread.latest_body}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem', flexShrink: 0 }}>
                <span style={timestamp}>{new Date(thread.latest_at).toLocaleString()}</span>
                <span style={badge}>{thread.reply_count} {thread.reply_count === 1 ? 'reply' : 'replies'}</span>
              </div>
            </button>

            {expanded === thread.lead_id && (
              <div style={{ borderTop: '1px solid #eee', padding: '0.75rem 1rem' }}>
                <ReplyThread leadId={thread.lead_id} />
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
