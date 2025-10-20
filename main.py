import json
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN
from browser_utils import launch_browser
from form_extractor import extract_form_fields
from field_classifier import classify_fields_with_gemini
from form_filler import autofill_form

# ── Load forms DB and users DB ──
with open("forms.json", "r") as f:
    forms = json.load(f)
with open("users.json", "r") as f:
    users_db = json.load(f)

pending_requests = {}

# Helper: wait until the browser page is closed or a timeout elapses
async def wait_until_page_closed(page, timeout: int = 300):
    try:
        await asyncio.wait_for(page.wait_for_event("close"), timeout=timeout)
    except asyncio.TimeoutError:
        # Timed out waiting for the user to close the page; proceed to cleanup
        pass

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

def get_form_url(prompt: str):
    prompt = prompt.lower()
    for key, info in forms.items():
        if key.lower() in prompt:
            return info["url"], key
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your **Playwright Form-Filling Assistant Bot**.\n\n"
        "Send a message like:\n"
        "👉 `I want to fill JEE form`\n"
        "👉 `Help me with Income Tax e-Pay`\n\n"
        "I'll send you a button to auto-fill the form instantly! 🚀"
    )
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.message.chat_id
    url, form_key = get_form_url(user_text)
    if not url:
        await update.message.reply_text("❌ Form not found in my database.")
        return
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    if not user_data:
        await update.message.reply_text("❌ Your user data is not in the database.")
        return
    request_id = f"{telegram_id}_{int(time.time())}"
    pending_requests[request_id] = {
        "url": url,
        "form_key": form_key,
        "user_data": user_data,
        "chat_id": chat_id
    }
    keyboard = [
        [InlineKeyboardButton("🚀 Open & Auto-Fill Form", callback_data=f"fill_{request_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📝 Found form: **{form_key}**\n"
        f"🌐 URL: {url}\n\n"
        f"Click the button below to open the form in a browser and auto-fill it instantly:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    if not callback_data.startswith("fill_"):
        return
    request_id = callback_data.replace("fill_", "")
    if request_id not in pending_requests:
        await query.edit_message_text("❌ Request expired or invalid.")
        return
    request = pending_requests[request_id]
    url = request["url"]
    user_data = request["user_data"]
    form_key = request["form_key"]
    await query.edit_message_text(
        f"🔄 Opening browser for: **{form_key}**\n"
        f"Please wait..."
    )
    try:
        p, browser, browser_context, page = await launch_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        for attempt in range(10):
            fields = await extract_form_fields(page)
            if fields:
                break
            await asyncio.sleep(1)
        print(f"\n📄 INITIAL: Extracted {len(fields)} fields")
        classified = classify_fields_with_gemini(fields, gemini_model)
        print(f"\n🤖 Classified {len(classified)} fields")
        filled_count = await autofill_form(page, classified, user_data)
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=f"✅ Form auto-filled!\n"
                 f"📊 Filled {filled_count} fields.\n\n"
                 f"👀 Please review the form in the browser and submit manually.\n"
                 f"The browser will stay open for up to 5 minutes, or closes sooner if you exit the window."
        )
        # Do not block for a fixed sleep; wait until the user closes the page or timeout
        await wait_until_page_closed(page, timeout=300)
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await p.stop()
        except Exception:
            pass
    except Exception as e:
        error_msg = f"❌ Error filling form: {str(e)}"
        print(error_msg)
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=error_msg
        )
    del pending_requests[request_id]

if __name__ == "__main__":
    # Enable concurrent handling of updates so a long-running fill does not block new messages
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Playwright Bot is running...")
    print("📱 Open Telegram and send a message to your bot!")
    app.run_polling()
