import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, setToken, getToken } from '../lib/api'

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (getToken()) navigate('/dashboard', { replace: true })
  }, [navigate])

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const token = await login(email, password)
      setToken(token)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: '#f5f5f5', fontFamily: 'sans-serif',
    }}>
      <div style={{
        background: '#fff', padding: '2rem', borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)', width: 340,
      }}>
        <h2 style={{ marginTop: 0, marginBottom: '1.5rem' }}>LeadForge — Sign in</h2>
        <form onSubmit={handleSubmit}>
          <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}>
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            autoFocus
            style={{ width: '100%', padding: '0.5rem', marginBottom: '1rem', boxSizing: 'border-box', borderRadius: 4, border: '1px solid #ccc' }}
          />
          <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.9rem' }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            style={{ width: '100%', padding: '0.5rem', marginBottom: '1.25rem', boxSizing: 'border-box', borderRadius: 4, border: '1px solid #ccc' }}
          />
          {error && (
            <p style={{ color: '#c62828', marginBottom: '1rem', fontSize: '0.9rem' }}>{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', padding: '0.6rem', background: '#1a1a2e',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: loading ? 'not-allowed' : 'pointer', fontSize: '1rem',
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
