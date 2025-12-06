// main.js
import { app } from "electron";
console.log("User data path:", app.getPath("userData"));
import express from "express";
import { saveUser } from "./storage.js";

app.whenReady().then(() => {
  const server = express();
  server.use(express.json());

  server.post("/user-details", (req, res) => {
    const received = req.body;
    const storedUser = saveUser(received);
    res.json({ status: "saved", user: storedUser });
  });

  server.listen(5000, () => console.log("Backend running inside Electron on port 5000"));
});
