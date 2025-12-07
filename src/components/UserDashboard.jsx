import "./UserDashboard.css";

function UserDashboard({ user, onLogout }) {
  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <div className="user-dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Welcome to Form Filler</h1>
          <p className="welcome-text">Hello, {user?.name || user?.telegram_id || "User"}!</p>
        </div>
        <button onClick={onLogout} className="logout-btn">
          Logout
        </button>
      </header>

      <div className="dashboard-content">
        <div className="user-info-card">
          <h2>Your Profile</h2>
          <div className="info-grid">
            <div className="info-item">
              <label>Telegram ID:</label>
              <span className="telegram-id">{user?.telegram_id || "N/A"}</span>
            </div>
            <div className="info-item">
              <label>Full Name:</label>
              <span>{user?.name || "Not provided"}</span>
            </div>
            <div className="info-item">
              <label>Email:</label>
              <span>{user?.email || "Not provided"}</span>
            </div>
            <div className="info-item">
              <label>Role:</label>
              <span className={`role-badge ${user?.role || "user"}`}>
                {user?.role || "user"}
              </span>
            </div>
            <div className="info-item">
              <label>Account Created:</label>
              <span>{formatDate(user?.created_at)}</span>
            </div>
            <div className="info-item">
              <label>Last Login:</label>
              <span>{formatDate(user?.last_login)}</span>
            </div>
          </div>
        </div>

        <div className="info-message">
          <p>You are logged in as a regular user. Contact an administrator for admin access.</p>
        </div>
      </div>
    </div>
  );
}

export default UserDashboard;

