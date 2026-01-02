import TelegramBot from "node-telegram-bot-api";

let bot = null;

// Initialize bot
export const initializeBot = (botToken) => {
  if (!botToken) {
    console.warn("Telegram bot token not provided. Bot features will be disabled.");
    return null;
  }

  try {
    bot = new TelegramBot(botToken, { polling: false });
    console.log("Telegram bot initialized successfully");
    return bot;
  } catch (error) {
    console.error("Error initializing Telegram bot:", error);
    return null;
  }
};

// Send verification code to user
export const sendVerificationCode = async (telegramId, code) => {
  if (!bot) {
    throw new Error("Telegram bot not initialized");
  }

  try {
    const message = `🔐 Verification Code\n\nYour verification code is: ${code}\n\nThis code will expire in 10 minutes.`;
    await bot.sendMessage(telegramId, message);
    return true;
  } catch (error) {
    console.error("Error sending verification code:", error);
    if (error.response?.statusCode === 403) {
      throw new Error("User has not started the bot. Please start the bot first.");
    } else if (error.response?.statusCode === 400) {
      throw new Error("Invalid Telegram ID");
    }
    throw new Error("Failed to send verification code");
  }
};

// Get bot username for link
export const getBotUsername = () => {
  // This should be set in environment variables
  return process.env.TELEGRAM_BOT_USERNAME || "your_bot_username";
};

