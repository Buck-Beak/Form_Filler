import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./Login.css";

function Login({ onLogin,user }) {
  const navigate = useNavigate();
  const [isRegistering, setIsRegistering] = useState(false);
  const [formData, setFormData] = useState({
    telegram_id: "",
    password: "",
    name: "",
    email: "",
    verification_code: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verificationSent, setVerificationSent] = useState(false);
  const [isVerified, setIsVerified] = useState(false);
  const [botLink, setBotLink] = useState("");
  const baseURL = "http://localhost:3000";

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError("");
    // Reset verification if telegram_id changes
    if (e.target.name === "telegram_id") {
      setIsVerified(false);
      setVerificationSent(false);
      setFormData(prev => ({ ...prev, verification_code: "" }));
    }
  };

  const handleVerifyTelegramId = async () => {
    if (!formData.telegram_id) {
      setError("Please enter your Telegram ID first");
      return;
    }

    // Validate telegram_id format
    if (!/^\d+$/.test(formData.telegram_id)) {
      setError("Invalid Telegram ID format. Please enter numbers only.");
      return;
    }

    setVerifying(true);
    setError("");

    try {
      const res = await fetch(`${baseURL}/api/verification/initiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_id: formData.telegram_id }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Failed to send verification code");
      }

      setVerificationSent(true);
      setBotLink(data.bot_link);
      
      // Open Telegram bot link
      if (data.bot_link) {
        window.open(data.bot_link, "_blank");
      }
    } catch (error) {
      console.error("Verification error:", error);
      setError(error.message);
    } finally {
      setVerifying(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!formData.verification_code) {
      setError("Please enter the verification code");
      return;
    }

    setVerifying(true);
    setError("");

    try {
      const res = await fetch(`${baseURL}/api/verification/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          telegram_id: formData.telegram_id,
          verification_code: formData.verification_code,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Invalid verification code");
      }

      setIsVerified(true);
      setError("");
      setVerificationSent(false);
    } catch (error) {
      console.error("Code verification error:", error);
      setError(error.message);
      setIsVerified(false);
    } finally {
      setVerifying(false);
    }
  };

  const handleSubmit = async (e) => {
    console.log(formData);
    e.preventDefault();
    setError("");
    
    // Check verification for registration
    if (isRegistering && !isVerified) {
      setError("Please verify your Telegram ID before registering");
      return;
    }
    
    setLoading(true);
    try {

      const endpoint = isRegistering
      ? "/api/user/register"
      : "/api/user/login";

    const payload = isRegistering
      ? {
          telegram_id: formData.telegram_id,
          name: formData.name,
          email: formData.email,
          password: formData.password,
        }
      : {
          telegram_id: formData.telegram_id,
          password: formData.password,
        };
      const res = await fetch(`${baseURL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const text = await res.text();
    console.log("Raw response:", text);

    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch (err) {
      throw new Error("Invalid JSON response from server");
    }

    console.log("Parsed responses:", data);
    console.log("isRegistering:", isRegistering);

    if (!res.ok) {
      console.log("Response not OK, status:", res.status);
      throw new Error(data.error || "Server error");
    }
    
    console.log("Response OK, proceeding...");
    
    if (!isRegistering) {
        // Login → call parent and navigate
        console.log("Login successful:", data);
        const loggedInUser = {
          telegram_id: data.telegram_id,
          name: data.name || "",
          email: data.email || "",
          role: "user",
        };
        console.log("Calling onLogin with:", loggedInUser);
        onLogin({ user: loggedInUser, token: data.token });
        console.log("Navigating to /user-dashboard");
        navigate("/user-dashboard");
      } else {
        // Registration → switch to login
        alert("Registration successful! Please login.");
        setIsRegistering(false);
        setFormData({ telegram_id: "", password: "", name: "", email: "" });
        navigate("/login");
      }
   } catch (error) {
      console.error("🔥 ERROR OCCURRED:", error);
      setError(error.message);
    }finally {
      setLoading(false);
    }
  };
  return (
    <div className="login-container">
      <div className="login-card">
        <h1>{isRegistering ? "Register" : "Login"}</h1>
        <p className="subtitle">
          {isRegistering
            ? "Create a new account to get started"
            : "Sign in to access the Form Filler app"}
        </p>

        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="telegramId">Telegram ID *</label>
            <div style={{ display: "flex", gap: "8px", alignItems: "flex-start" }}>
              <input
                type="text"
                id="telegramId"
                name="telegram_id"
                value={formData.telegram_id}
                onChange={handleChange}
                required
                placeholder="Enter your Telegram ID"
                style={{ flex: 1 }}
                disabled={isVerified}
              />
              {!isVerified && (
                <button
                  type="button"
                  onClick={handleVerifyTelegramId}
                  disabled={verifying || !formData.telegram_id}
                  style={{
                    padding: "10px 16px",
                    backgroundColor: "#007bff",
                    color: "white",
                    border: "none",
                    borderRadius: "4px",
                    cursor: verifying || !formData.telegram_id ? "not-allowed" : "pointer",
                    opacity: verifying || !formData.telegram_id ? 0.6 : 1,
                    whiteSpace: "nowrap",
                  }}
                >
                  {verifying ? "Sending..." : "Verify"}
                </button>
              )}
            </div>
            {isVerified && (
              <div style={{ marginTop: "8px", color: "#28a745", fontSize: "14px" }}>
                ✓ Telegram ID verified
              </div>
            )}
            {verificationSent && !isVerified && (
              <div style={{ marginTop: "8px" }}>
                <p style={{ fontSize: "14px", color: "#666", marginBottom: "8px" }}>
                  Verification code sent! Check your Telegram.
                </p>
                {botLink && (
                  <a
                    href={botLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: "#007bff",
                      textDecoration: "none",
                      fontSize: "14px",
                    }}
                  >
                    Open Telegram Bot →
                  </a>
                )}
              </div>
            )}
          </div>

          {verificationSent && !isVerified && (
            <div className="form-group">
              <label htmlFor="verificationCode">Verification Code *</label>
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  type="text"
                  id="verificationCode"
                  name="verification_code"
                  value={formData.verification_code}
                  onChange={handleChange}
                  placeholder="Enter 6-digit code"
                  maxLength="6"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  onClick={handleVerifyCode}
                  disabled={verifying || !formData.verification_code}
                  style={{
                    padding: "10px 16px",
                    backgroundColor: "#28a745",
                    color: "white",
                    border: "none",
                    borderRadius: "4px",
                    cursor: verifying || !formData.verification_code ? "not-allowed" : "pointer",
                    opacity: verifying || !formData.verification_code ? 0.6 : 1,
                  }}
                >
                  {verifying ? "Verifying..." : "Verify Code"}
                </button>
              </div>
            </div>
          )}

          {isRegistering && (
            <>
              <div className="form-group">
                <label htmlFor="name">Full Name</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Enter your full name"
                />
              </div>

              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="Enter your email"
                />
              </div>
            </>
          )}

          <div className="form-group">
            <label htmlFor="password">Password {isRegistering ? "(Optional)" : "*"}</label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required={!isRegistering}
              placeholder="Enter your password"
            />
          </div>

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? "Processing..." : isRegistering ? "Register" : "Login"}
          </button>
        </form>

        <div className="toggle-auth">
          <p>
            {isRegistering ? "Already have an account? " : "Don't have an account? "}
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setIsRegistering(!isRegistering);
                setError("");
                setFormData({ telegram_id: "", password: "", name: "", email: "" });
              }}
            >
              {isRegistering ? "Login" : "Register"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default Login;

