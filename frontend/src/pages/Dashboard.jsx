import { useState } from 'react'
import { healthCheck } from '../lib/api'

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  async function handleCheck() {
    setHealth(null)
    setError(null)
    try {
      const data = await healthCheck()
      setHealth(data)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <button onClick={handleCheck}>Check Backend Health</button>
      {health && <pre style={{ marginTop: '1rem' }}>{JSON.stringify(health, null, 2)}</pre>}
      {error && <p style={{ color: 'red', marginTop: '1rem' }}>{error}</p>}
    </div>
  )
}
