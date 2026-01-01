import express from "express";
const router = express.Router();
import {
  registerUser,
  loginUser,
  getUserById,
} from "../Controllers/userController.js";

router.post("/register", registerUser);
router.post("/login", loginUser);
router.get("/:userId", getUserById);

export default router;
