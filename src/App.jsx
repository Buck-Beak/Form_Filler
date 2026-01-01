import { useState, useEffect } from 'react'
import Login from './components/Login'
//import AdminDashboard from './components/AdminDashboard'
import UserDashboard from './components/UserDashboard'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
  const storedUser = localStorage.getItem("user");
  const storedToken = localStorage.getItem("authToken");

  if (storedUser && storedToken) {
    try {
      const parsedUser = JSON.parse(storedUser);

      setUser({
        telegram_id: parsedUser.telegram_id,
        name: parsedUser.name || "",
        email: parsedUser.email || "",
        role:
          parsedUser.role &&
          parsedUser.role.toLowerCase() === "admin"
            ? "admin"
            : "user"
      });
    } catch (err) {
      console.error("Invalid stored user", err);
      localStorage.clear();
    }
  }

  setLoading(false);
}, []);


  const handleLogin = (response) => {
    const { user, token } = response;

    const userWithRole = {
      telegram_id: user.telegram_id,
      name: user.name || "",
      email: user.email || "",
      role: user.role ? user.role.toLowerCase() : "user" // default to 'user'
    };

    setUser(userWithRole);

    localStorage.setItem("user", JSON.stringify(userWithRole));
    localStorage.setItem("authToken", token);
  };


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
