import { useState, useEffect } from 'react'
import { apiGet, getUserPlan } from '../lib/api'

export default function Experiments() {
  const plan = getUserPlan()
  const [experiments, setExperiments] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (plan !== 'enterprise') return
    apiGet('/experiments')
      .then(data => setExperiments(data))
      .catch(err => setError(err.message))
  }, [plan])

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
        <h3 style={{ marginTop: 0 }}>All Experiments</h3>

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
                {['ID', 'Name', 'Status', 'Created'].map(h => (
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
