import mongoose from "mongoose";

const VerificationSchema = new mongoose.Schema(
  {
    telegram_id: {
      type: String,
      required: true,
      index: true,
    },
    verification_code: {
      type: String,
      required: true,
    },
    expires_at: {
      type: Date,
      required: true,
      expires: 0, // Auto-delete after expires_at
    },
    verified: {
      type: Boolean,
      default: false,
    },
  },
  { timestamps: true }
);

// Auto-delete expired verifications
// `expires: 0` on the `expires_at` path already created the TTL index.
// Remove the explicit duplicate index declaration to avoid Mongoose warning.

export default mongoose.model("Verification", VerificationSchema);

