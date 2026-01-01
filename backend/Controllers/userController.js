import User from "../Models/userModel.js";
import jwt from "jsonwebtoken";

const createToken = (_id) => {
  return jwt.sign({ _id }, process.env.SECRET, { expiresIn: "3d" }); //content in payload of jwt
};

//register user
export const registerUser = async (req, res) => {
  const { telegram_id,name, email, password } = req.body;
  try {
    const user = await User.register(telegram_id,name, email, password);
    //create a token
    const token = createToken(user._id);

    res.status(200).json({
      _id: user._id,
      telegram_id,
      name,
      email,
      token,
    });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
};

//login user
export const loginUser = async (req, res) => {
  const { telegram_id, password } = req.body;

  try {
    const user = await User.login(telegram_id, password);
    //create a token
    const token = createToken(user._id);

    res.status(200).json({ telegram_id, token, userId: user._id });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
};

// GET /api/user/:userId
export const getUserById = async (req, res) => {
  try {
    const user = await User.findById(req.params.userId).select("name");
    if (!user) return res.status(404).json({ error: "User not found" });
    res.json(user);
  } catch (err) {
    res.status(500).json({ error: "Server error" });
  }
};
