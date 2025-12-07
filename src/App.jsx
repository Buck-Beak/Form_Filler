import { useState, useEffect } from 'react'
import Login from './components/Login'
import AdminDashboard from './components/AdminDashboard'
import UserDashboard from './components/UserDashboard'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check if user is already logged in
    const storedUser = localStorage.getItem('user')
    const storedToken = localStorage.getItem('authToken')
    
    if (storedUser && storedToken) {
      try {
        const parsedUser = JSON.parse(storedUser)
        // Ensure role is set correctly (default to 'user' if not admin)
        const userWithRole = {
          ...parsedUser,
          role: parsedUser.role && parsedUser.role.toLowerCase() === 'admin' ? 'admin' : 'user'
        }
        setUser(userWithRole)
        // Update localStorage with correct role
        localStorage.setItem('user', JSON.stringify(userWithRole))
      } catch (e) {
        console.error('Failed to parse stored user', e)
        localStorage.removeItem('user')
        localStorage.removeItem('authToken')
      }
    }
    setLoading(false)
  }, [])

  const handleLogin = (userData) => {
    // Ensure role is set correctly (default to 'user' if not admin)
    const userWithRole = {
      ...userData,
      role: userData.role && userData.role.toLowerCase() === 'admin' ? 'admin' : 'user'
    }
    setUser(userWithRole)
    // Update localStorage with correct role
    localStorage.setItem('user', JSON.stringify(userWithRole))
  }

  const handleLogout = () => {
    localStorage.removeItem('user')
    localStorage.removeItem('authToken')
    setUser(null)
  }

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    )
  }

  return (
    <div className="app">
      {user ? (
        // Check if user is admin - only admins can see Admin Dashboard
        // Use strict check: role must be exactly 'admin' (case-sensitive)
        user.role && user.role.toLowerCase() === 'admin' ? (
          <AdminDashboard user={user} onLogout={handleLogout} />
        ) : (
          <UserDashboard user={user} onLogout={handleLogout} />
        )
      ) : (
        <Login onLogin={handleLogin} />
      )}
    </div>
  )
}

export default App
