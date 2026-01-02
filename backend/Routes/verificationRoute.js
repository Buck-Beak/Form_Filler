import express from "express";
const router = express.Router();
import {
  initiateVerification,
  verifyCode,
  getVerificationStatus,
} from "../Controllers/verificationController.js";

router.post("/initiate", initiateVerification);
router.post("/verify", verifyCode);
router.get("/status/:telegram_id", getVerificationStatus);

export default router;

