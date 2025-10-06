
import os
import time
import json
import re
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ── Load environment variables 
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Initialise Gemini model ──
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By

# ─────────── Load User Data ───────────
with open("db.json", "r") as f:
    user_data = json.load(f)

# ─────────── Load Forms List ───────────
with open("forms.json", "r") as f:
    forms = json.load(f)

# ─────────── Selenium Form Extraction ───────────
def extract_form_fields(driver):
    """Extract input/textarea fields and their labels"""
    fields = []
    inputs = driver.find_elements(By.XPATH, "//input | //textarea")

    for inp in inputs:
        field_id = inp.get_attribute("id")
        field_name = inp.get_attribute("name")
        field_placeholder = inp.get_attribute("placeholder")
        field_type = inp.get_attribute("type")

        label_text = None
        if field_id:
            try:
                label_elem = driver.find_element(By.XPATH, f"//label[@for='{field_id}']")
                label_text = label_elem.text
            except:
                pass

        fields.append({
            "id": field_id,
            "name": field_name,
            "placeholder": field_placeholder,
            "type": field_type,
            "label": label_text
        })

    return fields


def classify_fields_with_gemini(fields):
    """Use Gemini to map form fields to categories like name, email, etc."""
    prompt = f"""
    You are given form fields from a webpage. 
    Each field has attributes: id, name, placeholder, type, and label.
    
    Classify each field into one of these categories:
    - name
    - email
    - password
    - phone
    - address
    - father_name
    - mother_name
    - aadhaar_number
    - date_of_birth
    - other

    Return JSON ONLY (no markdown, no explanation), format:
    [
      {{"id": "...", "category": "..."}},
      ...
    ]

    Fields:
    {fields}
    """

    response = gemini_model.generate_content(prompt)
    raw_text = response.text.strip()

    # Clean up any accidental code fences
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)

    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini output parse error:", raw_text, e)
        return []


def autofill_form(driver, classified_fields):
    """Fill fields using user data from db.json"""
    for mapping in classified_fields:
        field_id = mapping.get("id")
        category = mapping.get("category")

        value = user_data.get(category)
        if not value or not field_id:
            continue

        try:
            elem = driver.find_element(By.ID, field_id)
            elem.clear()
            elem.send_keys(str(value))
        except Exception as e:
            print(f"Could not fill {field_id}: {e}")


# ── Introductory /start command ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Bot started...")
    welcome_message = (
        "👋 Hello! I'm your **Form-Filling Assistant Bot**.\n\n"
        "You can tell me things like:\n"
        "👉 `I want to fill JEE Main form`\n"
        "👉 `Help me register for NEET`\n\n"
        "I'll guide you through the process and can even auto-fill details. 🚀"
    )
    await update.message.reply_text(welcome_message)

# ── Function to talk to Gemini ──
def ask_gemini(prompt: str) -> str:
    response = gemini_model.generate_content(prompt)
    return response.text.strip()

# ── Handle incoming messages ──
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower()
    print(f"User said: {user_text}")

    # Step 1: Find matching form key from forms.json
    matched_form = None
    for form_key in forms.keys():
        if form_key.lower() in user_text:
            matched_form = form_key
            break

    if not matched_form:
        await update.message.reply_text("❌ I couldn't find that form in my list.")
        return

    form_info = forms[matched_form]
    form_url = form_info["url"]
    await update.message.reply_text(f"📝 Opening form: {matched_form}\n🌐 URL: {form_url}")

    # Step 2: Open form with Selenium
    driver = webdriver.Chrome()
    driver.get(form_url)
    time.sleep(3)

    # Step 3: Extract → Classify → Autofill
    fields = extract_form_fields(driver)
    classified = classify_fields_with_gemini(fields)
    autofill_form(driver, classified)

    await update.message.reply_text("✅ Form auto-filled! Please review and submit manually.")
    time.sleep(10)
    driver.quit()

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build() 

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add the /start command handler
    app.add_handler(CommandHandler("start", start))

    # Add message handler for user text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()
