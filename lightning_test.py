import json
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ── Load environment variables ──
load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# ── Configure Gemini ──
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# ── Load forms DB and users DB ──
with open("forms.json", "r") as f:
    forms = json.load(f)
with open("users.json", "r") as f:
    users_db = json.load(f)

# ── Selenium setup ──
chrome_options = Options()
chrome_options.add_argument("--headless")  # Headless browser (no GUI)
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

# ── Extract input/textarea fields from a page using Selenium ──
def extract_form_fields(url):
    driver.get(url)
    fields = []

    inputs = driver.find_elements(By.XPATH, "//input | //textarea | //select")
    for inp in inputs:
        field_id = inp.get_attribute("id")
        field_name = inp.get_attribute("name")
        placeholder = inp.get_attribute("placeholder")
        field_type = inp.get_attribute("type")
        label_text = ""
        if field_id:
            try:
                label_elem = driver.find_element(By.XPATH, f"//label[@for='{field_id}']")
                label_text = label_elem.text.strip()
            except:
                pass
        fields.append({
            "id": field_id,
            "name": field_name,
            "placeholder": placeholder,
            "type": field_type,
            "label": label_text
        })
    return fields

# ── Classify fields using Gemini ──
def classify_fields_with_gemini(fields):
    prompt = f"""
You are given form fields from a webpage. 
Each field has attributes: id, name, placeholder, type, and label.

Classify each field into categories:
name, email, password, phone, address, father_name, mother_name, aadhaar_number, date_of_birth, other

Return JSON ONLY:
[
  {{"id": "...", "category": "..."}},
  ...
]

Fields:
{fields}
"""
    response = gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)

    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini parse error:", raw_text, e)
        return []

# ── Get form URL by user prompt ──
def get_form_url(prompt: str):
    prompt = prompt.lower()
    for key, info in forms.items():
        if key.lower() in prompt:
            return info["url"]
    return None

# ── Generate Lightning Autofill JSON ──
def generate_autofill_json(url, telegram_id):
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    if not user_data:
        return None, "User not found in database."

    fields = extract_form_fields(url)
    if not fields:
        return None, "No form fields detected."

    classified_fields = classify_fields_with_gemini(fields)

    autofill_data = {}
    for field in classified_fields:
        category = field.get("category")
        field_name = field.get("id") or field.get("name")
        if category in user_data and field_name:
            selector = f"input[name='{field_name}']"
            autofill_data[selector] = user_data[category]

    profile = [
        {
            "title": f"Autofill Profile for {url}",
            "url": url + "*",
            "fields": [{"selector": k, "value": v} for k, v in autofill_data.items()]
        }
    ]
    return profile, None

# ── Telegram commands ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your **Form-Filling Assistant Bot**.\n"
        "Send a message like 'I want to fill JEE form'.\n"
        "I will give you the form URL and generate Lightning Autofill JSON."
    )
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    user_text = update.message.text

    url = get_form_url(user_text)
    if not url:
        await update.message.reply_text("❌ Form not found.")
        return

    await update.message.reply_text(f"🔗 Form URL: {url}")

    json_profile, error = generate_autofill_json(url, telegram_id)
    if error:
        await update.message.reply_text(f"⚠️ {error}")
        return

    file_name = f"autofill_{telegram_id}.json"
    with open(file_name, "w") as f:
        json.dump(json_profile, f, indent=2)

    with open(file_name, "rb") as f:
        await update.message.reply_document(f, filename="autofill_profile.json")

    await update.message.reply_text("✅ Lightning Autofill JSON generated!")

# ── Run bot ──
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot running...")
    app.run_polling()
