import { NavLink, Outlet } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/leads', label: 'Leads' },
  { to: '/campaigns', label: 'Campaigns' },
]

export default function Layout() {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      <nav style={{
        width: 200,
        background: '#1a1a2e',
        color: '#fff',
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem 1rem',
        gap: '0.5rem',
      }}>
        <div style={{ fontWeight: 700, fontSize: '1.2rem', marginBottom: '1.5rem' }}>
          LeadForge
        </div>
        {NAV_LINKS.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            style={({ isActive }) => ({
              color: isActive ? '#4fc3f7' : '#ccc',
              textDecoration: 'none',
              padding: '0.4rem 0.6rem',
              borderRadius: 4,
              background: isActive ? 'rgba(255,255,255,0.08)' : 'transparent',
            })}
          >
            {label}
          </NavLink>
        ))}
        <div style={{ marginTop: 'auto' }}>
          <NavLink
            to="/login"
            style={{ color: '#ccc', textDecoration: 'none', fontSize: '0.9rem' }}
          >
            Login
          </NavLink>
        </div>
      </nav>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <header style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid #e0e0e0',
          background: '#fff',
          fontWeight: 600,
          fontSize: '1rem',
        }}>
          LeadForge AI System
        </header>
        <main style={{ flex: 1, padding: '1.5rem', background: '#f5f5f5' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
