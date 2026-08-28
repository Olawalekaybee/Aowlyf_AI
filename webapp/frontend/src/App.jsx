import { useState } from 'react'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('aowlyf_token'))
  const [staff, setStaff] = useState(() => {
    const raw = localStorage.getItem('aowlyf_staff')
    return raw ? JSON.parse(raw) : null
  })

  function handleLogin(newToken, newStaff) {
    setToken(newToken)
    setStaff(newStaff)
  }

  function handleLogout() {
    setToken(null)
    setStaff(null)
  }

  if (!token || !staff) {
    return <Login onLogin={handleLogin} />
  }
  return <Dashboard token={token} staff={staff} onLogout={handleLogout} />
}
