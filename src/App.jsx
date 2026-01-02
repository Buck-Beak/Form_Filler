import { HashRouter,Routes, Route } from "react-router-dom";
import { useState } from "react";
import Login from "./components/Login";
import UserDashboard from "./components/UserDashboard";

function App() {
  const [user, setUser] = useState(JSON.parse(localStorage.getItem("user")) || null);

  const handleLogin = ({ user, token }) => {
    setUser(user);
    localStorage.setItem("user", JSON.stringify(user));
    localStorage.setItem("authToken", token);
    console.log("User logged in:", user);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem("user");
    localStorage.removeItem("authToken");
  };

  // Check localStorage for user to handle navigation before state updates
  const getCurrentUser = () => {
    try {
      return user || JSON.parse(localStorage.getItem("user") || "null");
    } catch {
      return null;
    }
  };

  const currentUser = getCurrentUser();

  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={handleLogin} user={user} />} />
      <Route
        path="/user-dashboard"
        element={
          currentUser ? (
            <UserDashboard user={currentUser} onLogout={handleLogout} />
          ) : (
            <Login onLogin={handleLogin} user={user} />
          )
        }
      />
      <Route path="*" element={<Login onLogin={handleLogin} user={user} />} />
    </Routes>
  );
}

export default App;
