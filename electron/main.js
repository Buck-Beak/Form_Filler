// main.js

import { app, BrowserWindow } from "electron";
import path from "path";
import { fileURLToPath } from "url";
import pkg from "electron";
const { shell } = pkg;


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log("User data path:", app.getPath("userData"));
import express from "express";
import { saveUser, loadDB } from "./storage.js";

let mainWindow;

export function openDBLocation() {
  shell.openPath(app.getPath("userData"));
}

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

  // Save user details (existing endpoint)
  server.post("/user-details", (req, res) => {
    const received = req.body;
    console.log("Received user details:", received);
     if (!received?.telegram_id) {
      return res.status(400).json({ error: "telegram_id required" });
    }
    const storedUser = saveUser(received);

    if (!storedUser) {
      return res.status(404).json({
        error: "User not found. Update skipped."
      });
    }

    // Open the folder after save
    openDBLocation();

    const { password, ...userWithoutPassword } = storedUser;
    res.json({ status: "saved", user: userWithoutPassword });
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
