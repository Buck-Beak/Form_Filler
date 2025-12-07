const API_BASE_URL = "http://localhost:5000";

// Helper function to handle fetch errors
async function fetchWithErrorHandling(url, options) {
  try {
    // Create timeout controller
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
    
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: "Server error" }));
      throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error("Request timed out. Please check if the backend server is running on port 5000.");
    }
    if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError") || error.name === 'TypeError') {
      throw new Error("Cannot connect to backend server. Make sure:\n1. Electron app is running\n2. Backend server started on port 5000\n3. Check console for 'Backend running inside Electron on port 5000'");
    }
    throw error;
  }
}

export const api = {
  // Authentication
  async login(telegramId, password, name, email) {
    return fetchWithErrorHandling(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        telegram_id: telegramId,
        password,
        name,
        email,
      }),
    });
  },

  // Get all users (Admin)
  async getAllUsers() {
    return fetchWithErrorHandling(`${API_BASE_URL}/admin/users`, {
      method: "GET",
    });
  },

  // Get single user
  async getUser(telegramId) {
    return fetchWithErrorHandling(`${API_BASE_URL}/user/${telegramId}`, {
      method: "GET",
    });
  },

  // Promote user to admin (for development/testing)
  async promoteToAdmin(telegramId) {
    return fetchWithErrorHandling(`${API_BASE_URL}/admin/promote`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        telegram_id: telegramId,
      }),
    });
  },
};

