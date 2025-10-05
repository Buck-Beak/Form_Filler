
import os
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
model = genai.GenerativeModel('gemini-2.5-flash')

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
    response = model.generate_content(prompt)
    return response.text.strip()

# ── Handle incoming messages ──
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    print(f"User said: {user_text}")
    gemini_response = ask_gemini(
        f"The user said: '{user_text}'. Respond helpfully as a form-filling assistant."
    )

    await update.message.reply_text(gemini_response)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build() 

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add the /start command handler
    app.add_handler(CommandHandler("start", start))

    # Add message handler for user text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is running...")
    app.run_polling()
