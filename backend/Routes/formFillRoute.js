import express from "express";
import { createFormFill, getFormFillHistory } from "../Controllers/formFillController.js";

const router = express.Router();

// POST /api/form-fill
router.post("/", createFormFill);

// GET /api/form-fill/history/:telegram_id
router.get("/history/:telegram_id", getFormFillHistory);

export default router;
