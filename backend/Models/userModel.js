import mongoose from "mongoose";
import bcrypt from "bcrypt";
const UserSchema = new mongoose.Schema(
  {
    telegram_id:{
        type: String,
        required: true,
        unique: true,
    },
    name: {
      type: String,
      required: true,
    },
    email: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      minlength: 3,
    },
    password: {
      type: String,
      required: true,
      minlength: 6,
    },
  },
  { timestamps: true }
);

UserSchema.statics.register = async function (telegram_id, name, email, password) {
  if (!telegram_id || !name || !email || !password) {
    throw Error("All fields must be filled");
  }
  const exists = await this.findOne({ email });
  if (exists) {
    throw Error("Username already exists");
  }

  const salt = await bcrypt.genSalt(10);
  const hash = await bcrypt.hash(password, salt); //hashing the password

  const user = await this.create({ telegram_id, name, email, password: hash });
  return user;
};

UserSchema.statics.login = async function (telegram_id, password) {
  if (!telegram_id || !password) {
    throw Error("All fields must be filled");
  }

  const user = await this.findOne({ telegram_id });
  if (!user) {
    throw Error("Incorrect username");
  }

  const match = await bcrypt.compare(password, user.password);
  if (!match) {
    throw Error("Incorrect password");
  }

  return user;
};

export default mongoose.model("users", UserSchema);
