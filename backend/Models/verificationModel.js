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
VerificationSchema.index({ expires_at: 1 }, { expireAfterSeconds: 0 });

export default mongoose.model("Verification", VerificationSchema);

