import mongoose from "mongoose";

const FormFillSchema = new mongoose.Schema(
  {
    telegram_id: {
      type: String,
      required: true,
    },
    form_name: {
      type: String,
      required: true,
    },
    filled_fields: {
      type: Number,
      required: true,
    },
    timestamp: {
      type: Number,
      required: true,
    },
    datetime: {
      type: String,
      required: true,
    },
    form_url: {
      type: String,
      required: true,
    },
  },
  { timestamps: true }
);

export default mongoose.model("FormFill", FormFillSchema);
