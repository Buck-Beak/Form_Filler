import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./UserDashboard.css";

function HistoryPage({ user }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const baseURL = "http://localhost:3000";

  useEffect(() => {
    if (!user?.telegram_id) {
      setLoading(false);
      return;
    }

    const fetchHistory = async () => {
      try {
        setError("");
        const response = await fetch(`${baseURL}/api/form-fill/history/${user.telegram_id}`);
        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(`History request failed (${response.status}): ${text || response.statusText}`);
        }
        const json = await response.json();
        setHistory(json.records || []);
      } catch (err) {
        console.error("Error fetching history:", err);
        setError(err?.message || "Unable to load history");
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [user?.telegram_id]);

  if (loading) {
    return (
      <div className="user-dashboard">
        <div style={{ padding: "2rem", textAlign: "center" }}>Loading history...</div>
      </div>
    );
  }

  return (
    <div className="user-dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Form Fill History</h1>
          <p className="welcome-text">History for {user?.name || user?.telegram_id || "User"}</p>
        </div>
        <div className="dashboard-buttons">
          <button onClick={() => navigate("/user-dashboard")} className="logout-btn">
            Back to Dashboard
          </button>
        </div>
      </header>

      <div className="dashboard-content">
        {error && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        {history.length === 0 ? (
          <div className="info-message">
            <p>No history records found yet.</p>
          </div>
        ) : (
          <div className="user-info-card">
            <h2>Recent Submissions</h2>
            <div className="info-grid">
              {history.map((record) => (
                <div key={record._id} className="user-info-card" style={{ padding: "1rem" }}>
                  <div className="info-item">
                    <label>Form:</label>
                    <span>{record.form_name}</span>
                  </div>
                  <div className="info-item">
                    <label>Fields:</label>
                    <span>{record.filled_fields}</span>
                  </div>
                  <div className="info-item">
                    <label>Submitted:</label>
                    <span>{record.datetime}</span>
                  </div>
                  <div className="info-item">
                    <label>URL:</label>
                    <span>{record.form_url}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default HistoryPage;
