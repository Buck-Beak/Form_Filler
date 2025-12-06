// main.js
import { app } from "electron";
console.log("User data path:", app.getPath("userData"));
import express from "express";
import { saveUser,loadDB } from "./storage.js";

app.whenReady().then(() => {
  const server = express();
  server.use(express.json());

  server.post("/user-details", (req, res) => {
    const received = req.body;
    const storedUser = saveUser(received);
    res.json({ status: "saved", user: storedUser });
  });

  server.get("/user/:telegram_id", (req, res) => {
    const telegramId = req.params.telegram_id;
    const db = loadDB();
    const user = db.find(u => u.telegram_id == telegramId);

    if (!user) {
      return res.status(404).json({ error: "User not found" });
    }

    res.json(user);
  });

  server.listen(5000, () => console.log("Backend running inside Electron on port 5000"));
});
