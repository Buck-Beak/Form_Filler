import json
import time
import asyncio
import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN
from browser_utils import launch_browser
from form_extractor import extract_form_fields
from field_classifier import classify_fields_with_gemini
from form_filler import autofill_form
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

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded documents and extract user details"""
    telegram_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    # Get the document
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ No document received. Please upload a file.")
        return
    
    # Check file size (limit to 20MB)
    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large. Please upload a file smaller than 20MB.")
        return
    
    # Get file extension
    file_name = document.file_name or "document"
    file_extension = os.path.splitext(file_name)[1].lower()
    
    # Check if file type is supported
    supported_extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', 
                           '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    if file_extension not in supported_extensions:
        await update.message.reply_text(
            f"❌ Unsupported file type: {file_extension}\n\n"
            f"📋 Supported formats:\n"
            f"• PDF files (.pdf)\n"
            f"• Word documents (.docx, .doc)\n"
            f"• Excel files (.xlsx, .xls)\n"
            f"• Images (.jpg, .png, .gif, .bmp, .webp)\n"
            f"• Text files (.txt)"
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"📄 Processing document: **{file_name}**\n"
        f"🔄 Extracting text and analyzing with AI...\n"
        f"⏳ This may take a few moments..."
    )
    
    try:
        # Download the file
        file = await context.bot.get_file(document.file_id)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            await file.download_to_drive(temp_file.name)
            temp_file_path = temp_file.name
        
        try:
            # Process the document
            result = document_processor.process_document(temp_file_path, file_extension)
            
            if "error" in result:
                await processing_msg.edit_text(
                    f"❌ **Error processing document:**\n"
                    f"{result['error']}\n\n"
                    f"Please try with a different document or check if the file is readable."
                )
                return
            
            if not result.get("success"):
                await processing_msg.edit_text(
                    "❌ **Failed to extract user details from the document.**\n\n"
                    "The document might be:\n"
                    "• Empty or corrupted\n"
                    "• Not containing readable text\n"
                    "• In an unsupported format\n\n"
                    "Please try with a different document."
                )
                return
            
            user_details = result["user_details"]
            extracted_count = result["extracted_fields_count"]
            
            # Check if we have enough data to be useful
            if extracted_count < 3:
                await processing_msg.edit_text(
                    f"⚠️ **Limited data extracted**\n\n"
                    f"Only {extracted_count} fields were found in the document.\n"
                    f"This might not be enough for form filling.\n\n"
                    f"📋 **Extracted fields:**\n" +
                    "\n".join([f"• {k}: {v}" for k, v in user_details.items() if v is not None])
                )
                return
            
            # Find existing user or create new one
            existing_user_index = None
            for i, user in enumerate(users_db):
                if user.get("telegram_id") == telegram_id:
                    existing_user_index = i
                    break
            
            if existing_user_index is not None:
                # Update existing user
                existing_user = users_db[existing_user_index]
                updated_fields = []
                
                for key, value in user_details.items():
                    if value is not None and (key not in existing_user or existing_user[key] != value):
                        existing_user[key] = value
                        updated_fields.append(key)
                
                users_db[existing_user_index] = existing_user
                
                if updated_fields:
                    # Save updated users database
                    save_users_db()
                    
                    await processing_msg.edit_text(
                        f"✅ **Document processed successfully!**\n\n"
                        f"📊 **Extracted {extracted_count} fields** from the document\n"
                        f"🔄 **Updated {len(updated_fields)} fields** in your profile\n\n"
                        f"📋 **Updated fields:**\n" +
                        "\n".join([f"• {field}: {user_details[field]}" for field in updated_fields]) +
                        f"\n\n🎉 Your profile has been updated! You can now use form filling features."
                    )
                else:
                    await processing_msg.edit_text(
                        f"✅ **Document processed successfully!**\n\n"
                        f"📊 **Extracted {extracted_count} fields** from the document\n"
                        f"ℹ️ **No updates needed** - all data already exists in your profile\n\n"
                        f"📋 **Extracted fields:**\n" +
                        "\n".join([f"• {k}: {v}" for k, v in user_details.items() if v is not None])
                    )
            else:
                # Create new user
                new_user = {
                    "telegram_id": telegram_id,
                    "username": update.message.from_user.username,
                    **{k: v for k, v in user_details.items() if v is not None}
                }
                
                users_db.append(new_user)
                
                # Save updated users database
                save_users_db()
                
                await processing_msg.edit_text(
                    f"✅ **Document processed successfully!**\n\n"
                    f"📊 **Extracted {extracted_count} fields** from the document\n"
                    f"🆕 **Created new profile** for you\n\n"
                    f"📋 **Your profile data:**\n" +
                    "\n".join([f"• {k}: {v}" for k, v in user_details.items() if v is not None]) +
                    f"\n\n🎉 Profile created! You can now use form filling features."
                )
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass
    
    except Exception as e:
        await processing_msg.edit_text(
            f"❌ **Error processing document:**\n"
            f"{str(e)}\n\n"
            f"Please try again or contact support if the problem persists."
        )

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
