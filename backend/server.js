import dotenv from "dotenv";
dotenv.config(); // Load environment variables from .env file

import express from "express";
import mongoose from "mongoose";
import cors from "cors";

import userRoute from "./Routes/userRoute.js";
import verificationRoute from "./Routes/verificationRoute.js";
import { initializeBot } from "./Services/telegramBot.js";

const app = express();

app.use(express.json());
app.use(cors({
  origin: ["http://localhost:3000", "http://localhost:5173"],
  credentials: true
}));

// Initialize Telegram bot
initializeBot(process.env.TELEGRAM_BOT_TOKEN);

app.use("/api/user", userRoute);
app.use("/api/verification", verificationRoute);

const PORT = process.env.PORT || 3000;

mongoose
  .connect(process.env.MONGO_URI)
  .then(() => {
    app.listen(PORT, () => {
      console.log(`connected to db and listening on port ${PORT}`);
    });
  })
  .catch((error) => {
    console.log(error);
  });
