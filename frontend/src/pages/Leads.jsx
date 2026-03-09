import { useState, useEffect, useRef, Fragment } from 'react'
import { apiPost, apiGet } from '../lib/api'

const POLL_MS = 1500

const FACTOR_LABELS = {
  seniority_match: 'Seniority',
  title_match:     'Title',
  keyword_match:   'Keywords',
  location_match:  'Location',
  company_match:   'Company',
}

export default function Leads() {
  const [form, setForm] = useState({ keywords: '', location: '', company: '', limit: '5' })
  const [phase, setPhase] = useState('idle')   // idle | searching | polling | done | error
  const [jobId, setJobId] = useState(null)
  const [leads, setLeads] = useState([])
  const [error, setError] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [assign, setAssign] = useState({})         // { [lead_id]: { open, selected, status } }
  const [scoreExpanded, setScoreExpanded] = useState({}) // { [lead_id]: bool }
  const [sortOrder, setSortOrder] = useState('desc')     // 'desc' | 'asc'
  const [minScore, setMinScore] = useState(0)
  const [nlQuery, setNlQuery] = useState('')
  const [nlParsed, setNlParsed] = useState(null)
  const intervalRef = useRef(null)

  // Client-side derived view — filter then sort; original `leads` is never mutated.
  const displayLeads = leads
    .filter(l => (l.score ?? 0) >= minScore)
    .sort((a, b) =>
      sortOrder === 'desc'
        ? (b.score ?? 0) - (a.score ?? 0)
        : (a.score ?? 0) - (b.score ?? 0)
    )

  useEffect(() => {
    apiGet('/campaigns').then(setCampaigns).catch(() => {})
    return () => clearInterval(intervalRef.current)
  }, [])

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
                        <tr style={{ borderBottom: expanded ? 'none' : '1px solid #eee' }}>
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
                          <tr style={{ background: '#f9f9f9', borderBottom: '1px solid #eee' }}>
                            <td colSpan={6} style={{ padding: '0.4rem 0.75rem 0.65rem 0.75rem' }}>
                              <ScoreBreakdown explanation={lead.score_explanation} />
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
