import { useState } from 'react'
import { getToken } from '../lib/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export default function Settings() {
  const [userData, setUserData] = useState(null)
  const [error, setError] = useState(null)

  async function handleViewData() {
    setError(null)
    try {
      const res = await fetch(`${BASE_URL}/users/me/data`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      if (!res.ok) throw new Error(res.statusText)
      setUserData(await res.json())
    } catch (err) {
      setError(err.message)
    }
  }

  function handleExportData() {
    fetch(`${BASE_URL}/users/me/export`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(res => res.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'leadforge_user_export.json'
        a.click()
        window.URL.revokeObjectURL(url)
      })
      .catch(err => setError(err.message))
  }

  async function handleDeleteAccount() {
    if (!confirm('Delete your account permanently?')) return
    setError(null)
    try {
      const res = await fetch(`${BASE_URL}/users/me`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      if (!res.ok) throw new Error(res.statusText)
      localStorage.removeItem('token')
      window.location.href = '/login'
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Account Settings</h2>

      <section style={{ marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Privacy Controls</h3>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button onClick={handleViewData} style={btnStyle}>
            View My Data
          </button>
          <button onClick={handleExportData} style={btnStyle}>
            Export My Data
          </button>
          <button onClick={handleDeleteAccount} style={{ ...btnStyle, background: '#c62828', borderColor: '#c62828' }}>
            Delete My Account
          </button>
        </div>
      </section>

      {error && (
        <p style={{ color: '#c62828' }}>{error}</p>
      )}

      {userData && (
        <section>
          <h3 style={{ marginBottom: '0.5rem' }}>Your Data</h3>
          <pre style={{
            background: '#fff',
            border: '1px solid #e0e0e0',
            borderRadius: 4,
            padding: '1rem',
            overflowX: 'auto',
            fontSize: '0.85rem',
          }}>
            {JSON.stringify(userData, null, 2)}
          </pre>
        </section>
      )}
    </div>
  )
}

const btnStyle = {
  padding: '0.5rem 1rem',
  background: '#1a1a2e',
  color: '#fff',
  border: '1px solid #1a1a2e',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: '0.9rem',
}
