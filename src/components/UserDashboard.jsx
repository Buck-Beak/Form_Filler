import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./UserDashboard.css";

function UserDashboard({ user, onLogout }) {
  const [userDetails, setUserDetails] = useState(user);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const baseURL = "http://localhost:3000";
  const navigate = useNavigate();

  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  useEffect(() => {
    const fetchUserDetails = async () => {
      if (!user?.telegram_id) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const token = localStorage.getItem("authToken");
        const response = await fetch(`${baseURL}/api/user/${user.telegram_id}`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error("Failed to fetch user details");
        }

        const data = await response.json();
        setUserDetails(data);
        setError("");
      } catch (err) {
        console.error("Error fetching user details:", err);
        setError("Failed to load user details");
        // Fallback to the user prop if API fails
        setUserDetails(user);
      } finally {
        setLoading(false);
      }
    };

    fetchUserDetails();
  }, [user?.telegram_id]);

  const handleDatabaseClick = () => {
    navigate("/database");
  };

  if (loading) {
    return (
      <div className="user-dashboard">
        <div style={{ padding: "2rem", textAlign: "center" }}>Loading user details...</div>
      </div>
    );
  }

  return (
    <div className="user-dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Welcome to Form Filler</h1>
          <p className="welcome-text">Hello, {userDetails?.name || userDetails?.telegram_id || "User"}!</p>
        </div>
        <div className="dashboard-buttons">
          <button onClick={handleDatabaseClick} className="logout-btn">
            Database
          </button>
          <button onClick={() => navigate("/history")} className="logout-btn">
            History
          </button>
          <button onClick={onLogout} className="logout-btn">
            Logout
          </button>
        </div>
      </header>

      <div className="dashboard-content">
        {error && <div className="error-message" style={{ marginBottom: "1rem" }}>{error}</div>}
        
        <div className="user-info-card">
          <h2>Your Profile</h2>
          <div className="info-grid">
            <div className="info-item">
              <label>Telegram ID:</label>
              <span className="telegram-id">{userDetails?.telegram_id || "N/A"}</span>
            </div>
            <div className="info-item">
              <label>Full Name:</label>
              <span>{userDetails?.name || "Not provided"}</span>
            </div>
            <div className="info-item">
              <label>Email:</label>
              <span>{userDetails?.email || "Not provided"}</span>
            </div>
            <div className="info-item">
              <label>Role:</label>
              <span className={`role-badge ${userDetails?.role || "user"}`}>
                {userDetails?.role || "user"}
              </span>
            </div>
            <div className="info-item">
              <label>Account Created:</label>
              <span>{formatDate(userDetails?.createdAt)}</span>
            </div>
            <div className="info-item">
              <label>Last Updated:</label>
              <span>{formatDate(userDetails?.updatedAt)}</span>
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

