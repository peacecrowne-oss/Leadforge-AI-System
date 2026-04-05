import { useState, useEffect, useRef, Fragment } from 'react'
import { apiPost, apiGet, getToken } from '../lib/api'
import ReplyThread from '../components/ReplyThread'

const POLL_MS = 1500

const FACTOR_LABELS = {
  seniority_match: 'Seniority',
  title_match:     'Title',
  keyword_match:   'Keywords',
  location_match:  'Location',
  company_match:   'Company',
}

export default function Leads() {
  // ── DEBUG: set to a known job_id to load CSV/Apollo import results directly.
  // Set to null to use normal search flow.
  const debugJobId = "063b0afb-cd3e-431f-94c6-0c188896cc27"

  const [form, setForm] = useState({ keywords: '', location: '', company: '', limit: '5' })
  const [phase, setPhase] = useState('idle')   // idle | searching | polling | done | error
  const [jobId, setJobId] = useState(null)
  const [leads, setLeads] = useState([])
  const [error, setError] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [assign, setAssign] = useState({})         // { [lead_id]: { open, selected, status } }
  const [scoreExpanded, setScoreExpanded] = useState({}) // { [lead_id]: bool }
  const [threadExpanded, setThreadExpanded] = useState({}) // { [lead_id]: bool }
  const [sortOrder, setSortOrder] = useState('desc')     // 'desc' | 'asc'
  const [minScore, setMinScore] = useState(0)
  const [clientKeyword, setClientKeyword] = useState('')
  const [showLatestOnly, setShowLatestOnly] = useState(false)
  const [nlQuery, setNlQuery] = useState('')
  const [nlParsed, setNlParsed] = useState(null)
  const [jobs, setJobs] = useState([])   // recent job history (persisted in localStorage)
  const intervalRef = useRef(null)

  // Client-side derived view — filter then sort; original `leads` is never mutated.
  const kw = clientKeyword.toLowerCase()
  const latestJobId = showLatestOnly
    ? (leads.reduce((best, l) =>
        !best || (l.created_at || '') > (best.created_at || '') ? l : best
      , null)?.job_id ?? null)
    : null
  const displayLeads = leads
    .filter(l => !showLatestOnly || !latestJobId || l.job_id === latestJobId)
    .filter(l =>
      !kw ||
      (l.full_name  || '').toLowerCase().includes(kw) ||
      (l.title      || '').toLowerCase().includes(kw) ||
      (l.company    || '').toLowerCase().includes(kw)
    )
    .filter(l => (l.score ?? 0) >= minScore)
    .sort((a, b) =>
      sortOrder === 'desc'
        ? (b.score ?? 0) - (a.score ?? 0)
        : (a.score ?? 0) - (b.score ?? 0)
    )

  useEffect(() => {
    // Restore job history saved from previous sessions.
    try {
      const saved = JSON.parse(localStorage.getItem('leadforge_jobs') || '[]')
      setJobs(saved)
    } catch {}
    apiGet('/campaigns').then(setCampaigns).catch(() => {})
    return () => clearInterval(intervalRef.current)
  }, [])

  // When a search or import completes, save the job to history.
  useEffect(() => {
    if (phase === 'done' && jobId) {
      setJobs(prev => {
        if (prev.find(j => j.job_id === jobId)) return prev   // already recorded
        const entry = {
          job_id:        jobId,
          results_count: leads.length,
          created_at:    new Date().toISOString(),
        }
        const updated = [entry, ...prev].slice(0, 10)         // keep last 10
        localStorage.setItem('leadforge_jobs', JSON.stringify(updated))
        return updated
      })
    }
  }, [phase, jobId, leads.length])

  // Poll /leads/jobs/latest every 4 s. If a new job_id appears (e.g. auto_import_csv
  // ran externally), load its results automatically — but only when the component is
  // not already mid-search so we don't race with startPoll.
  const latestJobPollRef = useRef(null)
  const lastSeenJobId    = useRef(null)
  const lastSeenStatus   = useRef(null)

  useEffect(() => {
    const BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

    latestJobPollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BASE}/leads/jobs/latest`, {
          headers: { Authorization: `Bearer ${getToken()}` },
        })
        if (!res.ok) return
        const data = await res.json()

        const idle = phase === 'idle' || phase === 'done' || phase === 'error'
        const jobChanged  = data.job_id !== lastSeenJobId.current
        const nowComplete = data.status === 'complete' && lastSeenStatus.current !== 'complete'

        if (idle && (jobChanged || nowComplete)) {
          handleLoadJob(data.job_id)
        }

        lastSeenJobId.current  = data.job_id
        lastSeenStatus.current = data.status
      } catch {}
    }, 4000)

    return () => clearInterval(latestJobPollRef.current)
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  function toggleScore(leadId) {
    setScoreExpanded(s => ({ ...s, [leadId]: !s[leadId] }))
  }

  async function handleNlSearch(e) {
    e.preventDefault()
    clearInterval(intervalRef.current)
    setPhase('searching')
    setError(null)
    setLeads([])
    setAssign({})
    setScoreExpanded({})
    setNlParsed(null)
    try {
      const res = await apiPost('/leads/nl-search', { query: nlQuery })
      setNlParsed(res.parsed)
      setJobId(res.job_id)
      setPhase('polling')
      startPoll(res.job_id)
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  async function handleSearch(e) {
    e.preventDefault()
    clearInterval(intervalRef.current)
    setPhase('searching')
    setError(null)
    setLeads([])
    setAssign({})
    setScoreExpanded({})
    setNlParsed(null)
    try {
      const body = { limit: Math.max(1, Number(form.limit)) }
      if (form.keywords) body.keywords = form.keywords
      if (form.location) body.location = form.location
      if (form.company) body.company = form.company
      console.log('[Search Request]', body)
      const { job_id } = await apiPost('/leads/search', body)
      setJobId(job_id)
      setPhase('polling')
      startPoll(job_id)
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  async function handleLoadJob(jid) {
    clearInterval(intervalRef.current)
    setPhase('searching')
    setError(null)
    setLeads([])
    try {
      const res = await apiGet(`/leads/jobs/${jid}/results`)
      setLeads(res.results || [])
      setJobId(jid)
      setPhase('done')
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  async function handleImportCsv(e) {
    const file = e.target.files?.[0]
    if (!file) return
    clearInterval(intervalRef.current)
    setPhase('searching')
    setError(null)
    setLeads([])
    setAssign({})
    setScoreExpanded({})
    setNlParsed(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
      const res = await fetch(`${base}/leads/import/csv`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      })
      if (!res.ok) throw new Error(res.statusText)
      const data = await res.json()
      setJobId(data.job_id)
      setPhase('polling')
      startPoll(data.job_id)
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  async function handleLoadDebugJob() {
    if (!debugJobId) return
    setPhase('searching')
    setError(null)
    setLeads([])
    try {
      const res = await apiGet(`/leads/jobs/${debugJobId}/results`)
      setLeads(res.results || [])
      setJobId(debugJobId)
      setPhase('done')
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  function startPoll(jid) {
    console.log('[Leads] polling job_id:', jid)
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

  async function simulateReply(leadId) {
    try {
      await apiPost(`/leads/${leadId}/replies`, {
        body: "Hi, I'm interested in your service. Can you share more details?",
        sender_email: 'owner@restaurant.com',
        direction: 'inbound',
      })
      console.log('Reply created')
    } catch (err) {
      console.error('Failed to create reply:', err.message)
    }
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

      <section style={{ ...card, marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Natural Language Search</h3>
        <form onSubmit={handleNlSearch} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            value={nlQuery}
            onChange={e => setNlQuery(e.target.value)}
            placeholder="Find senior engineers in San Francisco"
            style={{ flex: 1, padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
          />
          <button type="submit" disabled={busy || !nlQuery.trim()} style={primaryBtn}>
            Search
          </button>
        </form>
        {nlParsed && (
          <div style={{ marginTop: '0.6rem', fontSize: '0.82rem', color: '#555', display: 'flex', gap: '0.5rem 1.25rem', flexWrap: 'wrap' }}>
            <span style={{ color: '#888' }}>Interpreted as:</span>
            {nlParsed.title    && <span><b>Title:</b> {nlParsed.title}</span>}
            {nlParsed.keywords && <span><b>Keywords:</b> {nlParsed.keywords}</span>}
            {nlParsed.location && <span><b>Location:</b> {nlParsed.location}</span>}
            {nlParsed.company  && <span><b>Company:</b> {nlParsed.company}</span>}
            <span><b>Limit:</b> {nlParsed.limit}</span>
          </div>
        )}
      </section>

      <section style={{ ...card, marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Import CSV</h3>
        <input
          type="file"
          accept=".csv"
          disabled={busy}
          onChange={handleImportCsv}
          style={{ fontSize: '0.9rem' }}
        />
      </section>

      {jobs.length > 0 && (
        <section style={{ ...card, marginBottom: '1rem' }}>
          <h3 style={{ marginTop: 0 }}>Recent Imports</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            {jobs.map(j => (
              <button
                key={j.job_id}
                onClick={() => handleLoadJob(j.job_id)}
                disabled={busy}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '0.45rem 0.75rem', border: '1px solid',
                  borderColor: j.job_id === jobId ? '#1a1a2e' : '#ddd',
                  borderRadius: 6, background: j.job_id === jobId ? '#f0f0f8' : '#fff',
                  cursor: 'pointer', fontSize: '0.85rem', textAlign: 'left',
                  fontWeight: j.job_id === jobId ? 600 : 400,
                }}
              >
                <span style={{ fontFamily: 'monospace', color: '#555' }}>
                  {j.job_id.slice(0, 8)}…
                </span>
                <span style={{ color: '#888' }}>
                  {j.results_count} lead{j.results_count !== 1 ? 's' : ''}
                  {j.created_at && (
                    <span style={{ marginLeft: '0.75rem' }}>
                      {new Date(j.created_at).toLocaleString()}
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {debugJobId && (
        <section style={{ ...card, marginBottom: '1rem', border: '1px dashed #f90' }}>
          <span style={{ fontSize: '0.82rem', color: '#888' }}>
            [DEBUG] job_id: <code>{debugJobId}</code>
          </span>
          <button onClick={handleLoadDebugJob} disabled={busy} style={{ ...primaryBtn, marginLeft: '1rem' }}>
            Load Results
          </button>
        </section>
      )}

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
        <>
          {/* ── Score controls ── */}
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginTop: '1rem', flexWrap: 'wrap' }}>
            <button onClick={() => setShowLatestOnly(v => !v)} style={smallBtn}>
              {showLatestOnly ? 'Show All' : 'Show Latest Only'}
            </button>
            <label style={ctrlLabel}>
              Filter results:
              <input
                type="text"
                value={clientKeyword}
                onChange={e => setClientKeyword(e.target.value)}
                placeholder="name, title, or company"
                style={{ ...ctrlSelect, width: '14rem' }}
              />
            </label>
            <label style={ctrlLabel}>
              Sort:
              <select value={sortOrder} onChange={e => setSortOrder(e.target.value)} style={ctrlSelect}>
                <option value="desc">Highest score first</option>
                <option value="asc">Lowest score first</option>
              </select>
            </label>
            <label style={ctrlLabel}>
              Min score:
              <select value={minScore} onChange={e => setMinScore(Number(e.target.value))} style={ctrlSelect}>
                <option value={0}>Any</option>
                <option value={0.3}>≥ 0.30</option>
                <option value={0.5}>≥ 0.50</option>
                <option value={0.7}>≥ 0.70</option>
              </select>
            </label>
            <span style={{ fontSize: '0.82rem', color: '#888', marginLeft: 'auto' }}>
              {displayLeads.length} of {leads.length} lead{leads.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* ── Empty-after-filter state ── */}
          {displayLeads.length === 0 ? (
            <p style={{ marginTop: '1rem', color: '#555' }}>
              No leads match the current score filter. Lower the minimum score or clear the filter.
            </p>
          ) : (
            <div style={{ ...card, marginTop: '0.75rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    {['Name', 'Title', 'Company', 'Location', 'Score', 'Action'].map(h => (
                      <th key={h} style={th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayLeads.map((lead, idx) => {
                    const a = assign[lead.id]
                    const expanded = !!scoreExpanded[lead.id]
                    const isTop = idx < 3
                    return (
                      <Fragment key={lead.id}>
                        <tr style={{ borderBottom: (expanded || threadExpanded[lead.id]) ? 'none' : '1px solid #eee' }}>
                          <td style={td}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              {lead.full_name}
                              {isTop && (
                                <span style={{
                                  fontSize: '0.7rem', fontWeight: 700, padding: '0.1rem 0.4rem',
                                  borderRadius: 8, background: '#e8f5e9', color: '#2e7d32',
                                  whiteSpace: 'nowrap',
                                }}>
                                  Top
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: '0.7rem', color: '#aaa', fontFamily: 'monospace', marginTop: '0.15rem' }}>
                              id: {lead.id}
                            </div>
                          </td>
                          <td style={td}>{lead.title || '—'}</td>
                          <td style={td}>{lead.company || '—'}</td>
                          <td style={td}>{lead.location || '—'}</td>
                          <td style={td}>
                            <button
                              onClick={() => toggleScore(lead.id)}
                              style={scoreCellBtn}
                              title={expanded ? 'Hide score details' : 'Show score details'}
                            >
                              {lead.score != null ? lead.score.toFixed(2) : '—'}
                              <span style={{ marginLeft: '0.3rem', fontSize: '0.7rem', opacity: 0.7 }}>
                                {expanded ? '▾' : '▸'}
                              </span>
                            </button>
                          </td>
                          <td style={td}>
                            <button
                              onClick={() => setThreadExpanded(t => ({ ...t, [lead.id]: !t[lead.id] }))}
                              style={{ ...smallBtn, marginBottom: '0.35rem' }}
                            >
                              {threadExpanded[lead.id] ? 'Hide Thread' : 'Thread'}
                            </button>
                            <button
                              onClick={() => simulateReply(lead.id)}
                              style={{ ...smallBtn, marginBottom: '0.35rem' }}
                            >
                              Simulate Reply
                            </button>
                            <button
                              onClick={() =>
                                apiGet(`/leads/${lead.id}/replies`)
                                  .then(r => console.log('[Test Fetch Replies]', lead.id, r))
                                  .catch(e => console.error('[Test Fetch Replies] error', e))
                              }
                              style={{ ...smallBtn, marginBottom: '0.35rem' }}
                            >
                              Test Fetch Replies
                            </button>
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
                        {expanded && (
                          <tr style={{ background: '#f9f9f9', borderBottom: threadExpanded[lead.id] ? 'none' : '1px solid #eee' }}>
                            <td colSpan={6} style={{ padding: '0.4rem 0.75rem 0.65rem 0.75rem' }}>
                              <ScoreBreakdown explanation={lead.score_explanation} />
                            </td>
                          </tr>
                        )}
                        {threadExpanded[lead.id] && (
                          <tr style={{ background: '#fafafa', borderBottom: '1px solid #eee' }}>
                            <td colSpan={6} style={{ padding: '0.6rem 0.75rem 0.75rem' }}>
                              <p style={{ margin: '0 0 0.5rem', fontSize: '0.78rem', fontWeight: 600, color: '#888', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                Conversation
                              </p>
                              <ReplyThread leadId={lead.id} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ScoreBreakdown({ explanation }) {
  if (!explanation || Object.keys(explanation).length === 0) {
    return (
      <span style={{ color: '#888', fontSize: '0.82rem' }}>No score details available.</span>
    )
  }
  return (
    <div style={{ display: 'flex', gap: '0.5rem 1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <span style={{ fontSize: '0.78rem', color: '#888', marginRight: '0.25rem' }}>Score breakdown:</span>
      {Object.entries(explanation).map(([key, val]) => (
        <div key={key} style={{ display: 'flex', alignItems: 'baseline', gap: '0.3rem', fontSize: '0.82rem' }}>
          <span style={{ color: '#555' }}>{FACTOR_LABELS[key] || key}</span>
          <span style={{
            fontWeight: 600,
            color: val >= 0.15 ? '#2e7d32' : val >= 0.08 ? '#e65100' : '#888',
          }}>
            {val.toFixed(2)}
          </span>
        </div>
      ))}
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
const scoreCellBtn = { background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 600, fontSize: '0.9rem', color: '#1a1a2e', display: 'flex', alignItems: 'center' }
const ctrlLabel = { fontSize: '0.85rem', color: '#555', display: 'flex', gap: '0.4rem', alignItems: 'center' }
const ctrlSelect = { padding: '0.25rem 0.4rem', border: '1px solid #ccc', borderRadius: 4, fontSize: '0.85rem', background: '#fff' }
const th = { padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 600 }
const td = { padding: '0.5rem 0.75rem', verticalAlign: 'middle' }
