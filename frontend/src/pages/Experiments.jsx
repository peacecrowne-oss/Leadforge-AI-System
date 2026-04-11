import { useState, useEffect } from 'react'
import { apiGet, apiPost, apiDelete, getUserPlan } from '../lib/api'

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
  const [selectedExperiments, setSelectedExperiments] = useState([])
  const [undoState, setUndoState] = useState({ items: [], visible: false })
  const [expandedExperiments, setExpandedExperiments] = useState({})
  const [variantTemplates, setVariantTemplates] = useState([])
  const [variantForm, setVariantForm] = useState({
    experimentId: null,
    name: '',
    message: '',
    traffic_percentage: 50,
    visible: false,
  })

  useEffect(() => {
    apiGet('/experiments/variant-templates')
      .then(setVariantTemplates)
      .catch(console.error)
  }, [])

  function fetchExperiments() {
    apiGet('/experiments')
      .then(data => setExperiments(data))
      .catch(err => setError(err.message))
  }

  useEffect(() => {
    if (plan !== 'enterprise') return
    fetchExperiments()
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

  async function handleDeleteSelected() {
    if (selectedExperiments.length === 0) return

    const confirmed = window.confirm("Are you sure you want to delete selected experiments?")
    if (!confirmed) return

    // Store backup for undo
    const deleted = experiments.filter(exp => selectedExperiments.includes(exp.id))

    for (const id of selectedExperiments) {
      await apiDelete(`/experiments/${id}`)
    }

    setSelectedExperiments([])
    fetchExperiments()

    // Show undo option
    setUndoState({ items: deleted, visible: true })

    // Auto-hide undo after 5 seconds
    setTimeout(() => {
      setUndoState({ items: [], visible: false })
    }, 5000)
  }

  async function handleUndoDelete() {
    for (const exp of undoState.items) {
      await apiPost('/experiments', exp)
    }
    fetchExperiments()
    setUndoState({ items: [], visible: false })
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
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={handleDeleteSelected}
              disabled={selectedExperiments.length === 0}
              style={smallBtn}
            >
              Delete Selected
            </button>
            <button onClick={() => setShowForm(f => !f)} style={smallBtn}>
              {showForm ? 'Cancel' : 'New Experiment'}
            </button>
          </div>
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

        {undoState.visible && (
          <div style={{ background: '#222', color: '#fff', padding: '10px', marginBottom: '10px', borderRadius: 4 }}>
            Experiments deleted
            <button onClick={handleUndoDelete} style={{ marginLeft: '10px' }}>
              Undo
            </button>
          </div>
        )}

        {experiments !== null && experiments.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                <th style={th}></th>
                {['ID', 'Name', 'Status', 'Created', 'Result', 'Actions'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {experiments.map(exp => (
                <tr key={exp.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={td}>
                    <input
                      type="checkbox"
                      checked={selectedExperiments.includes(exp.id)}
                      onChange={() => {
                        setSelectedExperiments(prev =>
                          prev.includes(exp.id)
                            ? prev.filter(id => id !== exp.id)
                            : [...prev, exp.id]
                        )
                      }}
                    />
                  </td>
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
                    <div style={{ marginBottom: '0.35rem' }}>
                      <button
                        onClick={() => {
                          setExpandedExperiments(prev => ({ ...prev, [exp.id]: !prev[exp.id] }))
                          if (!winnerResults[exp.id]) fetchWinner(exp.id)
                        }}
                        disabled={loadingResults[exp.id]}
                        style={smallBtn}
                      >
                        {loadingResults[exp.id] ? 'Loading...' : expandedExperiments[exp.id] ? 'Collapse' : 'View Result'}
                      </button>
                    </div>
                    {expandedExperiments[exp.id] && winnerResults[exp.id] ? (
                      <div>
                        <div><strong>{winnerResults[exp.id].winning_variant_name || 'No winner'}</strong></div>
                        <div style={{ fontSize: '0.75rem', color: '#666' }}>
                          {winnerResults[exp.id].confidence || ''}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '0.15rem' }}>
                          {winnerResults[exp.id].basis}
                        </div>
                      </div>
                    ) : (!expandedExperiments[exp.id] ? '—' : null)}
                    {expandedExperiments[exp.id] && metricsResults[exp.id] && (
                      <table style={{ marginTop: '0.5rem', borderCollapse: 'collapse', fontSize: '0.82rem', width: '100%' }}>
                        <thead>
                          <tr style={{ background: '#f0f0f0' }}>
                            <th style={th}>Variant</th>
                            <th style={th}>Exposures</th>
                            <th style={th}>Campaigns</th>
                          </tr>
                        </thead>
                        <tbody>
                          {metricsResults[exp.id].map(m => (
                            <tr key={m.variant_id} style={{ borderBottom: '1px solid #eee' }}>
                              <td style={td}>{m.variant_name}</td>
                              <td style={td}>{m.exposures}</td>
                              <td style={td}>{m.distinct_campaigns}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </td>
                  <td style={td}>
                    {exp.status !== 'completed' && (
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <button
                          onClick={() => setVariantForm({
                            experimentId: exp.id,
                            name: '',
                            message: '',
                            traffic_percentage: 50,
                            visible: true,
                          })}
                          style={smallBtn}
                        >Add Variant</button>
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
                    {variantForm.visible && variantForm.experimentId === exp.id && (
                      <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                          {variantTemplates.map(t => (
                            <button
                              key={t.name}
                              onClick={() => setVariantForm(prev => ({ ...prev, name: t.name, message: t.message }))}
                              style={smallBtn}
                            >
                              {t.name}
                            </button>
                          ))}
                        </div>
                        <input
                          value={variantForm.name}
                          placeholder="Variant name"
                          onChange={e => setVariantForm(prev => ({ ...prev, name: e.target.value }))}
                          style={{ padding: '0.3rem', border: '1px solid #ccc', borderRadius: 4, fontSize: '0.85rem' }}
                        />
                        <div style={{ marginBottom: '0.5rem' }}>
                          <button
                            onClick={() => setVariantForm(prev => ({
                              ...prev,
                              name: 'Variant A',
                              message: 'Hi, quick question — are you currently looking for more leads?'
                            }))}
                            style={smallBtn}
                          >
                            Use Variant A
                          </button>
                          <button
                            onClick={() => setVariantForm(prev => ({
                              ...prev,
                              name: 'Variant B',
                              message: 'Hi, I help businesses like yours generate qualified leads automatically. Open to a quick chat?'
                            }))}
                            style={{ ...smallBtn, marginLeft: '0.4rem' }}
                          >
                            Use Variant B
                          </button>
                        </div>
                        <textarea
                          value={variantForm.message}
                          placeholder="Message"
                          rows={3}
                          onChange={e => setVariantForm(prev => ({ ...prev, message: e.target.value }))}
                          style={{ padding: '0.3rem', border: '1px solid #ccc', borderRadius: 4, fontSize: '0.85rem', resize: 'vertical' }}
                        />
                        <input
                          type="number"
                          value={variantForm.traffic_percentage}
                          min={0}
                          max={100}
                          onChange={e => setVariantForm(prev => ({ ...prev, traffic_percentage: Number(e.target.value) }))}
                          style={{ padding: '0.3rem', border: '1px solid #ccc', borderRadius: 4, fontSize: '0.85rem', width: '80px' }}
                        />
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button
                            onClick={async () => {
                              try {
                                await apiPost(`/experiments/${variantForm.experimentId}/variants`, {
                                  name: variantForm.name,
                                  message: variantForm.message,
                                  traffic_percentage: variantForm.traffic_percentage,
                                })
                                setVariantForm({ ...variantForm, visible: false })
                                fetchExperiments()
                              } catch (err) {
                                setError(err.message)
                              }
                            }}
                            style={smallBtn}
                          >Save Variant</button>
                          <button
                            onClick={() => setVariantForm(prev => ({ ...prev, visible: false }))}
                            style={smallBtn}
                          >Cancel</button>
                        </div>
                      </div>
                    )}
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
