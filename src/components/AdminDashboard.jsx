import { useState, useEffect } from "react";
import { api } from "../api";
import "./AdminDashboard.css";

function AdminDashboard({ user, onLogout }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  // Security check: Only admins should access this
  useEffect(() => {
    if (user && (!user.role || user.role.toLowerCase() !== 'admin')) {
      // Redirect non-admin users immediately
      console.warn('Non-admin user attempted to access Admin Dashboard');
      onLogout();
      return;
    }
  }, [user, onLogout]);

  useEffect(() => {
    // Only load users if user is admin
    if (user && user.role === 'admin') {
      loadUsers();
      // Refresh users every 5 seconds
      const interval = setInterval(loadUsers, 5000);
      return () => clearInterval(interval);
    }
  }, [user]);

  const loadUsers = async () => {
    try {
      setError("");
      const data = await api.getAllUsers();
      setUsers(data.users || []);
    } catch (err) {
      setError(err.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter((u) => {
    const search = searchTerm.toLowerCase();
    return (
      u.telegram_id?.toLowerCase().includes(search) ||
      u.name?.toLowerCase().includes(search) ||
      u.email?.toLowerCase().includes(search)
    );
  });

  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <div className="admin-dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Admin Dashboard</h1>
          <p className="welcome-text">Welcome, {user?.name || user?.telegram_id || "Admin"}!</p>
        </div>
        <button onClick={onLogout} className="logout-btn">
          Logout
        </button>
      </header>

      <div className="dashboard-content">
        <div className="stats-section">
          <div className="stat-card">
            <div className="stat-value">{users.length}</div>
            <div className="stat-label">Total Users</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {users.filter((u) => {
                const lastLogin = u.last_login ? new Date(u.last_login) : null;
                const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
                return lastLogin && lastLogin > dayAgo;
              }).length}
            </div>
            <div className="stat-label">Active (24h)</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {users.filter((u) => u.role === "admin").length}
            </div>
            <div className="stat-label">Admins</div>
          </div>
        </div>

        <div className="users-section">
          <div className="section-header">
            <h2>User Management</h2>
            <div className="search-box">
              <input
                type="text"
                placeholder="Search users by ID, name, or email..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="search-input"
              />
              <button onClick={loadUsers} className="refresh-btn" title="Refresh">
                🔄
              </button>
            </div>
          </div>

          {error && <div className="error-message">{error}</div>}

          {loading ? (
            <div className="loading">Loading users...</div>
          ) : (
            <div className="users-table-container">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Telegram ID</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Created At</th>
                    <th>Last Login</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="no-data">
                        {searchTerm ? "No users found matching your search" : "No users registered yet"}
                      </td>
                    </tr>
                  ) : (
                    filteredUsers.map((u) => (
                      <tr key={u.telegram_id}>
                        <td className="telegram-id">{u.telegram_id}</td>
                        <td>{u.name || "—"}</td>
                        <td>{u.email || "—"}</td>
                        <td>
                          <span className={`role-badge ${u.role || "user"}`}>
                            {u.role || "user"}
                          </span>
                        </td>
                        <td className="date-cell">{formatDate(u.created_at)}</td>
                        <td className="date-cell">{formatDate(u.last_login)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminDashboard;

