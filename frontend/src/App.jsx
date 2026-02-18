import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

function App() {
  const [count, setCount] = useState(0)
  const [healthData, setHealthData] = useState(null)
  const [healthError, setHealthError] = useState(null)

  const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

  async function checkHealth() {
    setHealthData(null)
    setHealthError(null)
    try {
      const response = await fetch(`${BASE_URL}/health`)
      if (!response.ok) {
        setHealthError(`Server returned ${response.status} ${response.statusText}`)
        return
      }
      const data = await response.json()
      setHealthData(data)
    } catch (err) {
      setHealthError(`Request failed: ${err.message}`)
    }
  }

  return (
    <>
      <div>
        <a href="https://vite.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <h1>Vite + React</h1>
      <div className="card">
        <button onClick={() => setCount((count) => count + 1)}>
          count is {count}
        </button>
        <p>
          Edit <code>src/App.jsx</code> and save to test HMR
        </p>
      </div>
      <div className="card">
        <button onClick={checkHealth}>Check Backend Health</button>
        {healthData && (
          <pre style={{ textAlign: 'left', marginTop: '1rem' }}>
            {JSON.stringify(healthData, null, 2)}
          </pre>
        )}
        {healthError && (
          <p style={{ color: 'red', marginTop: '1rem' }}>{healthError}</p>
        )}
      </div>
      <p className="read-the-docs">
        Click on the Vite and React logos to learn more
      </p>
    </>
  )
}

export default App
