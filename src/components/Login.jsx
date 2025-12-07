import { useState } from "react";
import { api } from "../api";
import "./Login.css";

function Login({ onLogin }) {
  const [isRegistering, setIsRegistering] = useState(false);
  const [formData, setFormData] = useState({
    telegramId: "",
    password: "",
    name: "",
    email: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await api.login(
        formData.telegramId,
        formData.password,
        formData.name,
        formData.email
      );

      // Store auth info
      localStorage.setItem("authToken", result.token);
      localStorage.setItem("user", JSON.stringify(result.user));
      
      onLogin(result.user);
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
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
            <input
              type="text"
              id="telegramId"
              name="telegramId"
              value={formData.telegramId}
              onChange={handleChange}
              required
              placeholder="Enter your Telegram ID"
            />
          </div>

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
                setFormData({ telegramId: "", password: "", name: "", email: "" });
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

