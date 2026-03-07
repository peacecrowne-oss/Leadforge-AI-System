import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div>
      <h1>404 — Page Not Found</h1>
      <p><Link to="/">Return to Dashboard</Link></p>
    </div>
  )
}
