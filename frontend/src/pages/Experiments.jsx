import { useState, useEffect } from 'react'
import { apiGet, apiPost, getUserPlan } from '../lib/api'

export default function Experiments() {
  const plan = getUserPlan()
  const [experiments, setExperiments] = useState(null)
  const [campaigns, setCampaigns] = useState([])
  const [selectedCampaign, setSelectedCampaign] = useState({}) // { [experimentId]: campaignId }
  const [runFeedback, setRunFeedback] = useState({})           // { [experimentId]: message }
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [winnerResults, setWinnerResults] = useState({})   // { [experimentId]: winner result }
  const [metricsResults, setMetricsResults] = useState({}) // { [experimentId]: metrics list }
  const [loadingResults, setLoadingResults] = useState({}) // { [experimentId]: boolean }

  useEffect(() => {
    if (plan !== 'enterprise') return
    apiGet('/experiments')
      .then(data => setExperiments(data))
      .catch(err => setError(err.message))
    apiGet('/campaigns')
      .then(data => setCampaigns(data))
      .catch(() => {})
  }, [plan])

  async function handleComplete(id) {
    try {
      await apiPost(`/experiments/${id}/complete`)
      setExperiments(prev =>
        prev.map(exp => exp.id === id ? { ...exp, status: 'completed' } : exp)
      )
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleCreateExperiment(e) {
    e.preventDefault()
    if (!newName.trim()) return
    try {
      const created = await apiPost('/experiments', { name: newName.trim() })
      setExperiments(prev => [created, ...(prev || [])])
      setNewName('')
      setShowForm(false)
    } catch (err) {
      setError(err.message)
    }
  }

  async function fetchWinner(id) {
    if (winnerResults[id] && metricsResults[id]) return

    setLoadingResults(prev => ({ ...prev, [id]: true }))
    try {
      const result = await apiGet(`/experiments/${id}/winner`)
      const metrics = await apiGet(`/experiments/${id}/metrics`)
      setWinnerResults(prev => ({ ...prev, [id]: result }))
      setMetricsResults(prev => ({ ...prev, [id]: metrics }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingResults(prev => ({ ...prev, [id]: false }))
    }
  }

  async function handleRun(experimentId) {
    const campaignId = selectedCampaign[experimentId]
    if (!campaignId) {
      setRunFeedback(prev => ({ ...prev, [experimentId]: 'Select a campaign first.' }))
      return
    }
    try {
      await apiPost(`/campaigns/${campaignId}/run`)
      setRunFeedback(prev => ({ ...prev, [experimentId]: 'Campaign run successfully.' }))
    } catch (err) {
      setRunFeedback(prev => ({ ...prev, [experimentId]: err.message }))
    }
  }

  if (plan !== 'enterprise') {
    return (
      <div>
        <h1 style={{ marginTop: 0 }}>Experiments</h1>
        <div style={{ ...card, background: '#fff8e1', border: '1px solid #ffe082' }}>
          <h3 style={{ marginTop: 0, color: '#e65100' }}>Enterprise Feature</h3>
          <p style={{ margin: 0, color: '#555' }}>A/B testing experiments require an Enterprise plan.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Experiments</h1>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0 }}>All Experiments</h3>
          <button onClick={() => setShowForm(f => !f)} style={smallBtn}>
            {showForm ? 'Cancel' : 'New Experiment'}
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleCreateExperiment} style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Experiment name"
              required
              style={{ flex: 1, padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4, fontSize: '0.9rem' }}
            />
            <button type="submit" style={smallBtn}>Create</button>
          </form>
        )}

        {error && (
          <p style={{ color: '#c62828', fontSize: '0.9rem' }}>{error}</p>
        )}

        {experiments === null && !error && (
          <p style={{ color: '#888' }}>Loading…</p>
        )}

        {experiments !== null && experiments.length === 0 && (
          <p style={{ color: '#888' }}>No experiments found.</p>
        )}

        {experiments !== null && experiments.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                {['ID', 'Name', 'Status', 'Created', 'Result', 'Actions'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {experiments.map(exp => (
                <tr key={exp.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={td}>
                    <span
                      title="Click to copy ID"
                      onClick={() => navigator.clipboard.writeText(exp.id)}
                      style={{
                        fontFamily: 'monospace', fontSize: '0.8rem', color: '#555',
                        cursor: 'pointer', userSelect: 'all',
                      }}
                    >
                      {exp.id}
                    </span>
                  </td>
                  <td style={td}>{exp.name}</td>
                  <td style={td}>
                    <span style={{ ...badge, background: statusColor(exp.status) }}>
                      {exp.status}
                    </span>
                  </td>
                  <td style={td}>{new Date(exp.created_at).toLocaleDateString()}</td>
                  <td style={td}>
                    {exp.status === 'completed' && exp.winning_variant_id
                      ? <span>Winner: {exp.winning_variant_id.slice(0, 8)}…<br /><span style={{ color: '#888', fontSize: '0.8rem' }}>({exp.winner_basis})</span></span>
                      : <span style={{ color: '#aaa' }}>—</span>
                    }
                  </td>
                  <td style={td}>
                    {exp.status !== 'completed' && (
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <select
                          value={selectedCampaign[exp.id] || ''}
                          onChange={e => setSelectedCampaign(prev => ({ ...prev, [exp.id]: e.target.value }))}
                          style={{ fontSize: '0.85rem', padding: '0.2rem' }}
                        >
                          <option value=''>— select campaign —</option>
                          {campaigns.map(c => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </select>
                        <button onClick={() => handleRun(exp.id)} style={smallBtn}>Run</button>
                        <button onClick={() => handleComplete(exp.id)} style={smallBtn}>Complete</button>
                      </div>
                    )}
                    {runFeedback[exp.id] && (
                      <div style={{ fontSize: '0.8rem', marginTop: '0.25rem', color: '#555' }}>
                        {runFeedback[exp.id]}
                      </div>
                    )}
                    <div style={{ marginTop: '0.35rem' }}>
                      <button onClick={() => fetchWinner(exp.id)} disabled={loadingResults[exp.id]} style={smallBtn}>
                        {loadingResults[exp.id] ? 'Loading...' : 'View Result'}
                      </button>
                      {winnerResults[exp.id] && (
                        <div>
                          {winnerResults[exp.id].winning_variant_id ? (
                            <>
                              Winner: {winnerResults[exp.id].winning_variant_id.slice(0, 8)}…
                              <br />
                              ({winnerResults[exp.id].basis})
                              {metricsResults[exp.id] && (() => {
                                const m = metricsResults[exp.id].find(x => x.variant_id === winnerResults[exp.id].winning_variant_id)
                                return m ? <><br />Exposures: {m.exposures}</> : null
                              })()}
                            </>
                          ) : (
                            winnerResults[exp.id].basis
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function statusColor(s) {
  return {
    draft: '#888',
    running: '#2e7d32',
    paused: '#e65100',
    completed: '#1565c0',
  }[s] || '#888'
}

const card = { background: '#fff', padding: '1.25rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }
const th = { padding: '0.5rem 0.75rem', textAlign: 'left', fontWeight: 600 }
const td = { padding: '0.5rem 0.75rem', verticalAlign: 'middle' }
const badge = { color: '#fff', padding: '0.2rem 0.6rem', borderRadius: 10, fontSize: '0.8rem' }
const smallBtn = { padding: '0.25rem 0.6rem', cursor: 'pointer', border: '1px solid #ccc', borderRadius: 4, background: '#fff', fontSize: '0.85rem' }
