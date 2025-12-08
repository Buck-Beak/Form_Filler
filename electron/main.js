// main.js
import { app, BrowserWindow } from "electron";
import path from "path";
import { fileURLToPath } from "url";


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log("User data path:", app.getPath("userData"));
import express from "express";
import { saveUser, loadDB } from "./storage.js";

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Load the app
  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  console.log("Electron app is ready");
  createWindow();
  console.log("Electron window created");

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  console.log("Starting Express server...");
  const server = express();
  server.use(express.json());
  console.log("Express middleware configured");
  
  // Enable CORS for frontend requests
  server.use((req, res, next) => {
    res.header("Access-Control-Allow-Origin", "*");
    res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
    res.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
    if (req.method === "OPTIONS") {
      return res.sendStatus(200);
    }
    next();
  });

  // Register/Login endpoint
  server.post("/auth/login", (req, res) => {
    const { telegram_id, password, name, email } = req.body;
    const db = loadDB();
    
    if (!telegram_id) {
      return res.status(400).json({ error: "Telegram ID is required" });
    }

    let user = db.find(u => u.telegram_id === telegram_id);
    
    if (!user) {
      // New user registration
      const newUser = {
        telegram_id,
        password: password || "", // In production, hash this
        name: name || "",
        email: email || "",
        role: "user",
        created_at: new Date().toISOString(),
        last_login: new Date().toISOString()
      };
      saveUser(newUser);
      return res.json({ 
        status: "registered", 
        user: { ...newUser, password: undefined },
        token: "mock_token_" + telegram_id // In production, use JWT
      });
    } else {
      // Existing user login
      if (password && user.password !== password) {
        return res.status(401).json({ error: "Invalid password" });
      }
      
      // Update last login
      user.last_login = new Date().toISOString();
      saveUser(user);
      
      return res.json({ 
        status: "logged_in", 
        user: { ...user, password: undefined },
        token: "mock_token_" + telegram_id
      });
    }
  });

  // Get all users (Admin only)
  server.get("/admin/users", (req, res) => {
    // In production, verify admin token/role from request headers
    // For now, we allow access but frontend should check role
    const db = loadDB();
    // Remove passwords from response
    const users = db.map(u => {
      const { password, ...userWithoutPassword } = u;
      return userWithoutPassword;
    });
    res.json({ users, count: users.length });
  });

  // Get single user
  server.get("/user/:telegram_id", (req, res) => {
    const telegramId = req.params.telegram_id;
    const db = loadDB();
    const user = db.find(u => u.telegram_id == telegramId);

    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }

    const { password, ...userWithoutPassword } = user;
    res.json(userWithoutPassword);
  });

  // Save user details (existing endpoint)
  server.post("/user-details", (req, res) => {
    const received = req.body;
    const storedUser = saveUser(received);
    const { password, ...userWithoutPassword } = storedUser;
    res.json({ status: "saved", user: userWithoutPassword });
  });

  // Promote user to admin (for testing/development)
  server.post("/admin/promote", (req, res) => {
    const { telegram_id } = req.body;
    const db = loadDB();
    const user = db.find(u => u.telegram_id === telegram_id);
    
    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }
    
    user.role = "admin";
    saveUser(user);
    const { password, ...userWithoutPassword } = user;
    res.json({ 
      status: "promoted", 
      message: "User promoted to admin",
      user: userWithoutPassword 
    });
  });

  server.listen(5000, () => {
    console.log("✅ Backend running inside Electron on port 5000");
    console.log("✅ Server is ready to accept requests");
  }).on('error', (err) => {
    console.error("❌ Failed to start server:", err.message);
    if (err.code === 'EADDRINUSE') {
      console.error("❌ Port 5000 is already in use. Please close the application using that port.");
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
