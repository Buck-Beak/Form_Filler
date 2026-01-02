import Verification from "../Models/verificationModel.js";
import { sendVerificationCode, getBotUsername } from "../Services/telegramBot.js";

// Generate a 6-digit verification code
const generateVerificationCode = () => {
  return Math.floor(100000 + Math.random() * 900000).toString();
};

// POST /api/verification/initiate
export const initiateVerification = async (req, res) => {
  try {
    const { telegram_id } = req.body;

    if (!telegram_id) {
      return res.status(400).json({ error: "Telegram ID is required" });
    }

    // Validate telegram_id format (should be numeric)
    if (!/^\d+$/.test(telegram_id)) {
      return res.status(400).json({ error: "Invalid Telegram ID format" });
    }

    // Delete any existing verification for this telegram_id
    await Verification.deleteMany({ telegram_id });

    // Generate verification code
    const code = generateVerificationCode();
    const expiresAt = new Date(Date.now() + 10 * 60 * 1000); // 10 minutes from now

    // Save verification code
    const verification = await Verification.create({
      telegram_id,
      verification_code: code,
      expires_at: expiresAt,
      verified: false,
    });

    // Send code via Telegram bot
    try {
      await sendVerificationCode(telegram_id, code);
    } catch (error) {
      // Delete the verification if sending fails
      await Verification.deleteOne({ _id: verification._id });
      return res.status(400).json({ 
        error: error.message || "Failed to send verification code",
        bot_username: getBotUsername()
      });
    }

    const botUsername = getBotUsername();
    const botLink = `https://t.me/${botUsername}`;

    res.status(200).json({
      message: "Verification code sent to your Telegram",
      bot_link: botLink,
      expires_in: 600, // 10 minutes in seconds
    });
  } catch (error) {
    console.error("Error initiating verification:", error);
    res.status(500).json({ error: "Server error" });
  }
};

// POST /api/verification/verify
export const verifyCode = async (req, res) => {
  try {
    const { telegram_id, verification_code } = req.body;

    if (!telegram_id || !verification_code) {
      return res.status(400).json({ error: "Telegram ID and verification code are required" });
    }

    // Find verification
    const verification = await Verification.findOne({
      telegram_id,
      verification_code,
      verified: false,
    });

    if (!verification) {
      return res.status(400).json({ error: "Invalid or expired verification code" });
    }

    // Check if expired
    if (new Date() > verification.expires_at) {
      await Verification.deleteOne({ _id: verification._id });
      return res.status(400).json({ error: "Verification code has expired" });
    }

    // Mark as verified
    verification.verified = true;
    await verification.save();

    res.status(200).json({
      message: "Telegram ID verified successfully",
      verified: true,
    });
  } catch (error) {
    console.error("Error verifying code:", error);
    res.status(500).json({ error: "Server error" });
  }
};

// GET /api/verification/status/:telegram_id
export const getVerificationStatus = async (req, res) => {
  try {
    const { telegram_id } = req.params;

    const verification = await Verification.findOne({
      telegram_id,
      verified: true,
    });

    if (!verification) {
      return res.status(404).json({ verified: false });
    }

    res.status(200).json({ verified: true });
  } catch (error) {
    console.error("Error checking verification status:", error);
    res.status(500).json({ error: "Server error" });
  }
};

