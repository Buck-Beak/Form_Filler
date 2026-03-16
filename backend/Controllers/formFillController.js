import FormFill from "../Models/formFillModel.js";

export const createFormFill = async (req, res) => {
  try {
    const { telegram_id, form_name, filled_fields, timestamp, datetime, form_url } = req.body;

    if (!telegram_id || !form_name || filled_fields == null || !timestamp || !datetime || !form_url) {
      return res.status(400).json({ error: "Missing required fields" });
    }

    const record = await FormFill.create({
      telegram_id,
      form_name,
      filled_fields,
      timestamp,
      datetime,
      form_url,
    });

    res.status(201).json({ message: "Form fill record saved", record });
  } catch (error) {
    console.error("Error saving form fill record:", error);
    res.status(500).json({ error: "Server error" });
  }
};

export const getFormFillHistory = async (req, res) => {
  try {
    const { telegram_id } = req.params;
    if (!telegram_id) {
      return res.status(400).json({ error: "telegram_id required" });
    }

    const records = await FormFill.find({ telegram_id }).sort({ createdAt: -1 });
    res.status(200).json({ records });
  } catch (error) {
    console.error("Error fetching form fill history:", error);
    res.status(500).json({ error: "Server error" });
  }
};
