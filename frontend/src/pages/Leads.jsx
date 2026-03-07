import { useState, useEffect, useRef } from 'react'
import { apiPost, apiGet } from '../lib/api'

const POLL_MS = 1500

export default function Leads() {
  const [form, setForm] = useState({ keywords: '', location: '', company: '', limit: '5' })
  const [phase, setPhase] = useState('idle')   // idle | searching | polling | done | error
  const [jobId, setJobId] = useState(null)
  const [leads, setLeads] = useState([])
  const [error, setError] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [assign, setAssign] = useState({})     // { [lead_id]: { open, selected, status } }
  const intervalRef = useRef(null)

  useEffect(() => {
    apiGet('/campaigns').then(setCampaigns).catch(() => {})
    return () => clearInterval(intervalRef.current)
  }, [])

  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  async function handleSearch(e) {
    e.preventDefault()
    clearInterval(intervalRef.current)
    setPhase('searching')
    setError(null)
    setLeads([])
    setAssign({})
    try {
      const body = { limit: Math.max(1, Number(form.limit)) }
      if (form.keywords) body.keywords = form.keywords
      if (form.location) body.location = form.location
      if (form.company) body.company = form.company
      const { job_id } = await apiPost('/leads/search', body)
      setJobId(job_id)
      setPhase('polling')
      startPoll(job_id)
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  function startPoll(jid) {
    intervalRef.current = setInterval(async () => {
      try {
        const job = await apiGet(`/leads/jobs/${jid}`)
        if (job.status === 'complete') {
          clearInterval(intervalRef.current)
          const res = await apiGet(`/leads/jobs/${jid}/results`)
          setLeads(res.results || [])
          setPhase('done')
        } else if (job.status === 'failed') {
          clearInterval(intervalRef.current)
          setError('Search job failed.')
          setPhase('error')
        }
      } catch (err) {
        clearInterval(intervalRef.current)
        setError(err.message)
        setPhase('error')
      }
    }, POLL_MS)
  }

  function openAssign(leadId) {
    setAssign(a => ({ ...a, [leadId]: { open: true, selected: campaigns[0]?.id || '', status: 'idle' } }))
  }

  async function confirmAssign(lead) {
    const state = assign[lead.id]
    if (!state?.selected) return
    setAssign(a => ({ ...a, [lead.id]: { ...a[lead.id], status: 'adding' } }))
    try {
      await apiPost(`/campaigns/${state.selected}/leads`, { job_id: jobId, lead_id: lead.id })
      setAssign(a => ({ ...a, [lead.id]: { ...a[lead.id], status: 'added' } }))
    } catch (err) {
      const msg = err.status === 409 ? 'Already assigned' : err.message
      setAssign(a => ({ ...a, [lead.id]: { ...a[lead.id], status: 'err', errMsg: msg } }))
    }
  }

  const busy = phase === 'searching' || phase === 'polling'

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Lead Search</h1>

      <div style={card}>
        <form onSubmit={handleSearch}>
          <div style={grid}>
            <Field label="Keywords" value={form.keywords} onChange={set('keywords')} />
            <Field label="Location" value={form.location} onChange={set('location')} />
            <Field label="Company" value={form.company} onChange={set('company')} />
            <Field label="Limit" value={form.limit} onChange={set('limit')} type="number" min="1" max="50" />
          </div>
          <button type="submit" disabled={busy} style={{ ...primaryBtn, marginTop: '1rem' }}>
            {busy ? 'Searching…' : 'Search Leads'}
          </button>
        </form>
      </div>

      {error && <p style={{ color: '#c62828', marginTop: '1rem' }}>{error}</p>}
      {phase === 'done' && leads.length === 0 && (
        <p style={{ marginTop: '1rem', color: '#555' }}>No leads found for these filters.</p>
      )}

      {leads.length > 0 && (
        <div style={{ ...card, marginTop: '1rem', overflowX: 'auto' }}>
          <h3 style={{ marginTop: 0 }}>{leads.length} lead{leads.length !== 1 ? 's' : ''} found</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                {['Name', 'Title', 'Company', 'Location', 'Score', 'Action'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map(lead => {
                const a = assign[lead.id]
                return (
                  <tr key={lead.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={td}>{lead.full_name}</td>
                    <td style={td}>{lead.title || '—'}</td>
                    <td style={td}>{lead.company || '—'}</td>
                    <td style={td}>{lead.location || '—'}</td>
                    <td style={td}>{lead.score != null ? lead.score.toFixed(2) : '—'}</td>
                    <td style={td}>
                      {!a?.open ? (
                        <button
                          onClick={() => openAssign(lead.id)}
                          disabled={campaigns.length === 0}
                          style={smallBtn}
                          title={campaigns.length === 0 ? 'Create a campaign first' : ''}
                        >
                          {campaigns.length === 0 ? 'No campaigns' : 'Add to Campaign'}
                        </button>
                      ) : a.status === 'added' ? (
                        <span style={{ color: '#2e7d32', fontSize: '0.85rem' }}>✓ Added</span>
                      ) : (
                        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                          <select
                            value={a.selected}
                            onChange={e => setAssign(as => ({ ...as, [lead.id]: { ...as[lead.id], selected: e.target.value } }))}
                            style={{ fontSize: '0.85rem', padding: '0.2rem 0.4rem', borderRadius: 4, border: '1px solid #ccc' }}
                          >
                            {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                          </select>
                          <button
                            onClick={() => confirmAssign(lead)}
                            disabled={a.status === 'adding'}
                            style={smallBtn}
                          >
                            {a.status === 'adding' ? '…' : 'Add'}
                          </button>
                          {a.status === 'err' && (
                            <span style={{ color: '#c62828', fontSize: '0.8rem' }}>{a.errMsg}</span>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Field({ label, value, onChange, type = 'text', ...rest }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem' }}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        style={{ width: '100%', padding: '0.4rem', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: 4 }}
        {...rest}
      />
    </div>
  )
}

const card = { background: '#fff', padding: '1.25rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: '0.75rem' }
const primaryBtn = { padding: '0.45rem 1.25rem', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.95rem' }
const smallBtn = { padding: '0.25rem 0.6rem', cursor: 'pointer', border: '1px solid #ccc', borderRadius: 4, background: '#fff', fontSize: '0.85rem' }
const th = { padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 600 }
const td = { padding: '0.5rem 0.75rem', verticalAlign: 'middle' }
