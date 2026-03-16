import json
import time
import asyncio
import os
import tempfile
import requests
import aiohttp  # async HTTP client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN
from browser_utils import launch_browser
from form_extractor import extract_form_fields
from field_classifier import classify_fields_with_gemini
from form_filler import autofill_form
from generate_form_url import generate_form_url
from document_processor import DocumentProcessor

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

# Initialize document processor
document_processor = DocumentProcessor(gemini_model)

def save_users_db():
    """Safely save users database to file"""
    try:
        with open("users.json", "w") as f:
            json.dump(users_db, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving users database: {e}")
        return False

def load_users_db():
    """Safely load users database from file"""
    try:
        with open("users.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading users database: {e}")
        return []

def get_form_url(prompt: str):
    prompt = prompt.lower()
    for key, info in forms.items():
        if key.lower() in prompt:
            return info["url"], key
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your **Playwright Form-Filling Assistant Bot**.\n\n"
        "📋 **What I can do:**\n"
        "• Fill forms automatically using your data\n"
        "• Extract user details from uploaded documents\n\n"
        "📝 **To fill forms:** Send a message like:\n"
        "👉 `I want to fill JEE form`\n"
        "👉 `Help me with Income Tax e-Pay`\n\n"
        "📄 **To extract data:** Upload any document (PDF, Word, Excel, Image, Text)\n"
        "I'll extract your details and add them to the database! 🚀\n\n"
        "Use /help for more information."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "🤖 **Bot Commands:**\n\n"
        "📝 **Form Filling:**\n"
        "• Send text like 'I want to fill [form name]'\n"
        "• I'll find the form and auto-fill it for you\n\n"
        "📄 **Document Processing:**\n"
        "• Upload documents (PDF, Word, Excel, Images, Text)\n"
        "• I'll extract your personal details using AI\n"
        "• Data will be saved to your profile\n\n"
        "📋 **Supported Document Types:**\n"
        "• PDF files (.pdf)\n"
        "• Word documents (.docx, .doc)\n"
        "• Excel files (.xlsx, .xls)\n"
        "• Images (.jpg, .png, .gif, .bmp, .webp)\n"
        "• Text files (.txt)\n\n"
        "🔒 **Privacy:** Your data is processed securely and stored locally."
    )
    await update.message.reply_text(help_message)

# sending json to standalone app after extracting fields from document
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded documents, extract user details, and send JSON to standalone app"""

    # Get Telegram user info
    telegram_id = update.message.from_user.id
    file_message = update.message.document

    if not file_message:
        await update.message.reply_text("❌ No document received.")
        return

    # File size check
    if file_message.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large. Max allowed is 20MB.")
        return

    # Determine file extension
    file_name = file_message.file_name or "document"
    file_extension = os.path.splitext(file_name)[1].lower()

    supported = [
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"
    ]

    if file_extension not in supported:
        await update.message.reply_text(
            f"❌ Unsupported file type `{file_extension}`.\n"
            f"Supported: PDF, DOCX, XLSX, Images, TXT"
        )
        return

    # Notify user
    status_msg = await update.message.reply_text(
        f"📄 Processing `{file_name}`...\n"
        f"⏳ Extracting text and analyzing with AI..."
    )

    try:
        # Download file to temp path
        telegram_file = await context.bot.get_file(file_message.file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            await telegram_file.download_to_drive(tmp.name)
            temp_path = tmp.name

        # Process document through your Standalone AI processor
        try:
            result = document_processor.process_document(temp_path, file_extension)

            if "error" in result:
                await status_msg.edit_text(f"❌ Error: {result['error']}")
                return

            if not result.get("success"):
                await status_msg.edit_text(
                    "❌ Could not extract useful data.\n"
                    "Try with a clearer or different document."
                )
                return

            extracted_json = result["user_details"]
            extracted_count = result["extracted_fields_count"]

        finally:
            os.unlink(temp_path)

        # =========== 🚀 NEW PART — SEND JSON TO STANDALONE SERVER ===========

        try:
            payload = {
                "telegram_id": telegram_id,
                "file_name": file_name,
                "extracted_fields": extracted_json,
                "fields_count": extracted_count
            }

            send_res = requests.post("http://localhost:5000/user-details", json=payload).json()

            await status_msg.edit_text(
                f"✅ Document processed!\n\n"
                f"📤 **Sent extracted JSON to Standalone App**\n"
                f"🌐 Server Response: `{send_res}`\n\n"
                f"📋 **Extracted Fields ({extracted_count})**:\n" +
                "\n".join([f"• {k}: {v}" for k, v in extracted_json.items() if v])
            )

        except Exception as e:
            await status_msg.edit_text(
                f"⚠️ Document processed but failed to send to server.\n"
                f"Error: {e}"
            )

    except Exception as e:
        await status_msg.edit_text(f"❌ Error processing document:\n{str(e)}")



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.message.chat_id
    url, form_key = await generate_form_url(user_text,gemini_model)
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
        "chat_id": chat_id,
        "telegram_id": telegram_id
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
    # user_data = request["user_data"]

    # fetch data from electron app
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://localhost:5000/user/{request['telegram_id']}") as resp:
            if resp.status == 200:
                user_data = await resp.json()
                print("\n📥 RECEIVED FROM ELECTRON APP:", user_data)

            else:
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text="❌ Could not load your saved data from the standalone app."
                )
                return

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
        filled_count = await autofill_form(page, classified, user_data['extracted_fields'])
        
        # ========== SEND FORM FILL DETAILS TO STANDALONE APP ==========
        try:
            form_fill_data = {
                "telegram_id": request['telegram_id'],
                "form_name": form_key,
                "filled_fields": filled_count,
                "timestamp": time.time(),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "form_url": url
            }
            
            # Send to standalone app
            response = requests.post("http://localhost:5000/form-fill", json=form_fill_data, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ Form fill details sent to standalone app: {form_fill_data}")
            else:
                print(f"⚠️ Failed to send form fill details: {response.status_code}")
                
        except Exception as e:
            print(f"⚠️ Error sending form fill details: {e}")
        
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
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    
    # Add message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Add callback query handler
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Playwright Bot with Document Processing is running...")
    print("📱 Open Telegram and send a message to your bot!")
    print("📄 Upload documents to extract user details!")
    app.run_polling()
