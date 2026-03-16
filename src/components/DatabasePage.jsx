import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./UserDashboard.css";

function DatabasePage({ user }) {
  const [telegramData, setTelegramData] = useState(null);
  const [telegramError, setTelegramError] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const electronAPI = "http://localhost:5000";

  useEffect(() => {
    if (!user?.telegram_id) {
      setLoading(false);
      return;
    }

    const fetchTelegramData = async () => {
      try {
        setTelegramError("");
        const response = await fetch(`${electronAPI}/user-details/${user.telegram_id}`);
        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(
            `Telegram data request failed (${response.status}): ${text || response.statusText}`
          );
        }
        const json = await response.json();
        setTelegramData(json.user || null);
      } catch (err) {
        console.error("Error fetching telegram data:", err);
        setTelegramError(err?.message || "Unable to load Telegram-sourced data");
        setTelegramData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchTelegramData();
  }, [user?.telegram_id]);

  if (loading) {
    return (
      <div className="user-dashboard">
        <div style={{ padding: "2rem", textAlign: "center" }}>Loading database...</div>
      </div>
    );
  }

  return (
    <div className="user-dashboard">
      <header className="dashboard-header">
        <div>
          <h1>Database</h1>
          <p className="welcome-text">Telegram-sourced data for {user?.name || user?.telegram_id || "User"}</p>
        </div>
        <div className="dashboard-buttons">
          <button onClick={() => navigate("/user-dashboard")} className="logout-btn">
            Back to Dashboard
          </button>
        </div>
      </header>

      <div className="dashboard-content">
        {telegramError && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            {telegramError}
          </div>
        )}

        {telegramData ? (
          <div className="user-info-card">
            <h2>Extracted Data</h2>
            <div className="info-grid">
              <div className="info-item">
                <label>File Name:</label>
                <span>{telegramData.file_name || "N/A"}</span>
              </div>
              <div className="info-item">
                <label>Fields received:</label>
                <span>{telegramData.fields_count ?? 0}</span>
              </div>
              <div className="info-item" style={{ gridColumn: "1 / -1" }}>
                <label>Extracted Fields:</label>
                {telegramData.extracted_fields && Object.keys(telegramData.extracted_fields).length > 0 ? (
                  <div className="extracted-fields">
                    {Object.entries(telegramData.extracted_fields).map(([key, value]) => 
                      value !== null ? (
                        <div key={key} className="field-row">
                          <span className="field-key">{key}:</span>
                          <span className="field-value">{String(value)}</span>
                        </div>
                      ) : null
                    )}
                  </div>
                ) : (
                  <span className="muted">No extracted fields yet.</span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="info-message">
            <p>No database records found for this user.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default DatabasePage;