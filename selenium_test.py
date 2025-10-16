import os
import time
import json
import re
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.by import By

# ── Load environment variables 
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Initialise Gemini model ──
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# ── Load Users and Forms ──
with open("users.json", "r") as f:
    users_list = json.load(f)

with open("forms.json", "r") as f:
    forms = json.load(f)

# ── Helper to get user by Telegram ID ──
def get_user_by_telegram_id(telegram_id):
    for user in users_list:
        if user.get("telegram_id") == telegram_id:
            return user
    return None

# ── Selenium Form Extraction ──
def extract_form_fields(driver):
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

# ── Gemini Classification ──
def classify_fields_with_gemini(fields):
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
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)
    print("Gemini response:", raw_text)

    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini output parse error:", raw_text, e)
        return []

# ── Autofill form using Selenium ──
def autofill_form(driver, classified_fields, telegram_id):
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        print(f"User with telegram_id {telegram_id} not found.")
        return

    for mapping in classified_fields:
        field_id = mapping.get("id")
        category = mapping.get("category")
        value = user.get(category)
        if not value or not field_id:
            continue

        try:
            elem = driver.find_element(By.ID, field_id)
            elem.clear()
            elem.send_keys(str(value))
        except Exception as e:
            print(f"Could not fill {field_id}: {e}")

# ── Telegram /start command ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your **Form-Filling Assistant Bot**.\n\n"
        "You can tell me things like:\n"
        "👉 `I want to fill JEE Main form`\n"
        "👉 `Help me register for NEET`\n\n"
        "I'll guide you through the process and can auto-fill details. 🚀"
    )
    await update.message.reply_text(welcome_message)

# ── Handle incoming messages ──
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.lower()
    chat_id = update.message.chat_id
    telegram_id = update.message.from_user.id
    print(f"User said: {user_text}")

    # Step 1: Match form
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

    # Ask user to open form manually
    await update.message.reply_text(
        f"🌐 Please open this form in your Chrome browser manually:\n\n{form_url}\n\n"
        f"After opening the form, type **'done'** here to continue auto-filling."
    )

    # Temporary handler to wait for "done"
    async def wait_for_done(done_update: Update, done_context: ContextTypes.DEFAULT_TYPE):
        if done_update.message.text.lower().strip() != "done":
            await done_update.message.reply_text("❌ Please type 'done' once you've opened the form.")
            return

        # Remove this temporary handler
        done_context.application.remove_handler(temp_handler)

        await done_update.message.reply_text("✅ Attaching to your Chrome...")

        # Step 2: Attach to existing Chrome session
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Chrome(options=chrome_options)

        # Step 3: Extract, classify, autofill
        fields = extract_form_fields(driver)
        classified = classify_fields_with_gemini(fields)
        autofill_form(driver, classified, telegram_id)

        await done_update.message.reply_text("✅ Form auto-filled! Please review and submit manually.")

    # Add temporary handler
    temp_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, wait_for_done)
    context.application.add_handler(temp_handler)

# ── Run the bot ──
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running...")
    app.run_polling()
