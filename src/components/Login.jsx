import { useState } from "react";
import "./Login.css";

function Login() {
  const [isRegistering, setIsRegistering] = useState(false);
  const [formData, setFormData] = useState({
    telegram_id: "",
    password: "",
    name: "",
    email: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const baseURL = "http://localhost:3000";

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError("");
  };

  const handleSubmit = async (e) => {
    console.log(formData);
    e.preventDefault();
    setError("");
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

    console.log("Parsed response:", data);

    if (!res.ok) {
      throw new Error(data.error || "Server error");
    }
   } catch (error) {
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
            <input
              type="text"
              id="telegramId"
              name="telegram_id"
              value={formData.telegram_id}
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

