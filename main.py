import json
import time
import asyncio
import os
import tempfile
import requests
import aiohttp  # async HTTP client
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN
from browser_utils import launch_browser
from form_extractor import extract_form_fields
from field_classifier import classify_fields_with_gemini
from form_filler import autofill_form
from document_processor import DocumentProcessor
from navigation_agent import NavigationAgent, NavigationBlockedError
from crawler import WebCrawler
from captcha_handler import CaptchaHandler
from login_handler import LoginHandler
from dynamic_url_extractor import find_best_url

# ── Load forms DB and users DB ──
with open("forms.json", "r") as f:
    forms = json.load(f)
with open("users.json", "r") as f:
    users_db = json.load(f)
with open("official_forms_urls.json", "r") as f:
    official_urls = json.load(f)

pending_requests = {}
active_crawlers = {}  # telegram_id -> WebCrawler instance

# Helper: wait until the browser page is closed or a timeout elapses
async def wait_until_page_closed(page, timeout: int = 300):
    try:
        # Disable internal playwright 30s timeout, rely on asyncio.wait_for
        await asyncio.wait_for(page.wait_for_event("close", timeout=0), timeout=timeout)
    except asyncio.TimeoutError:
        # Timed out waiting for the user to close the page; proceed to cleanup
        pass

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# Initialize document processor
document_processor = DocumentProcessor(gemini_model)

# Module-level handler instances shared across all sessions.
# bot is injected lazily inside button_handler before each crawl run.
captcha_handler = CaptchaHandler()
login_handler   = LoginHandler(users_db=users_db)

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

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's Telegram ID and registration status"""
    telegram_id = update.message.from_user.id
    username = update.message.from_user.username or "N/A"
    first_name = update.message.from_user.first_name or ""
    
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    
    if user_data:
        status_msg = (
            f"✅ **You are registered!**\n\n"
            f"👤 Name: {user_data.get('name', 'N/A')}\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"📧 Email: {user_data.get('email', 'N/A')}\n"
            f"📱 Mobile: {user_data.get('mobile', 'N/A')}"
        )
    else:
        status_msg = (
            f"❌ **You are NOT registered yet!**\n\n"
            f"🆔 Your Telegram ID: `{telegram_id}`\n"
            f"👤 Telegram Name: {first_name}\n"
            f"🔤 Username: @{username}\n\n"
            f"📝 To register:\n"
            f"1. Upload a document with your details OR\n"
            f"2. Ask admin to add this ID to users.json:\n\n"
            f"```json\n"
            f'{{\n'
            f'  "telegram_id": {telegram_id},\n'
            f'  "name": "{first_name}",\n'
            f'  "email": "your@email.com",\n'
            f'  "mobile": "1234567890",\n'
            f'  "dob": "2000-01-01"\n'
            f'}}\n'
            f"```"
        )
    
    await update.message.reply_text(status_msg)

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to local test website"""
    # Manually set text to 'test' so handle_message picks it up
    update.message.text = "test"
    await handle_message(update, context)

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

    # ── Intercept credential replies ──────────────────────────────────────
    if login_handler.is_waiting_for_creds(telegram_id):
        if login_handler.signal_credentials_received(telegram_id, user_text):
            await update.message.reply_text(
                "✅ Credentials received! Attempting login…"
            )
            return
        else:
            await update.message.reply_text(
                "⚠️ Please use the format  `username:password`",
                parse_mode="Markdown",
            )
            return

    # ── Intercept OTP replies ─────────────────────────────────────────────
    if login_handler.is_waiting_for_otp(telegram_id):
        if login_handler.signal_otp_received(telegram_id, user_text):
            await update.message.reply_text("✅ OTP received! Continuing…")
            return
    # ── Intercept 'continue' / 'next' (Human Resume) ─────────────────────
    if user_text.lower().strip() in ["continue", "next", "resume"]:
        if telegram_id in active_crawlers:
            crawler = active_crawlers[telegram_id]
            if crawler.nav_agent.is_paused:
                crawler.nav_agent.is_paused = False
                await update.message.reply_text("🚀 Resuming navigation...")
                return
            else:
                await update.message.reply_text("ℹ️ Bot is already working. No need to resume.")
                return
        else:
            await update.message.reply_text("❌ No active navigation to resume.")
            return

    # ── Intercept 'test' command ──────────────────────────────────────────
    if user_text.lower().strip() == "test":
        url = "http://localhost:8000"
        form_key = "Local Test Website"
    else:
        url, form_key = get_form_url(user_text)
    
    # If not found, use dynamic AI-powered extractor
    if not url:
        await update.message.reply_text("🔍 Searching for the best matching form using AI...")
        url, form_key, reason = await find_best_url(user_text, forms, gemini_model, official_urls)
        
        if not url:
            await update.message.reply_text(
                f"❌ Could not find a matching form.\n"
                f"Reason: {reason}\n\n"
                f"Try asking for one of these:\n" +
                "\n".join([f"• {k}" for k in forms.keys()])
            )
            return
        
        await update.message.reply_text(
            f"✅ Found matching form: **{form_key}**\n"
            f"Reason: {reason}"
        )
    
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    if not user_data:
        await update.message.reply_text("❌ Your user data is not in the database.\nUse /myid to register.")
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

    # ── CAPTCHA "Done" button ─────────────────────────────────────────────
    if callback_data.startswith("captcha_done_"):
        chat_id_str = callback_data.replace("captcha_done_", "")
        try:
            captcha_handler.signal_captcha_solved(int(chat_id_str))
            await query.edit_message_caption(
                caption="✅ CAPTCHA acknowledged! Continuing navigation…"
            )
        except Exception:
            await query.answer("✅ Got it! Continuing…")
        return

    if not callback_data.startswith("fill_"):
        return
    request_id = callback_data.replace("fill_", "")
    if request_id not in pending_requests:
        await query.edit_message_text("❌ Request expired or invalid.")
        return
    request = pending_requests[request_id]
    telegram_id = request["telegram_id"]
    url = request["url"]
    form_key = request["form_key"]

    # Always load base data from users.json for preferences
    base_user_data = next((u for u in users_db if u["telegram_id"] == request["telegram_id"]), {})
    
    # Try to fetch data from standalone app (extracted fields)
    extracted_data = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:5000/user/{request['telegram_id']}", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    extracted_data = await resp.json()
                    print("\n📥 RECEIVED FROM ELECTRON APP:", extracted_data)
    except Exception as e:
        print(f"⚠️ Standalone app not reachable: {e}")
        print("📂 Using only users.json")
    
    # Merge preferences with extracted fields
    # If server has "extracted_fields", use them. Otherwise use base_user_data.
    if extracted_data and "extracted_fields" in extracted_data:
        # Create a copy of base preferences
        final_fields = base_user_data.copy()
        # Update with extracted fields from server
        final_fields.update(extracted_data["extracted_fields"])
        user_data = {"extracted_fields": final_fields}
    else:
        # Fallback: wrap base_user_data
        user_data = {"extracted_fields": base_user_data}

    if not base_user_data and not extracted_data:
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text="❌ Your user data is not in the database. Use /myid to check your registration status."
        )
        return

    form_key = request["form_key"]
    await query.edit_message_text(
        f"🔄 Opening browser for: **{form_key}**\n"
        f"🧭 Navigating to form page...\n"
        f"(The crawler may navigate through login pages, solve CAPTCHAs, \n"
        f"and explore the site to reach the form — this may take 1–3 minutes)"
    )
    try:
        p, browser, browser_context, page = await launch_browser()

        # Inject bot reference into shared handlers for this session
        captcha_handler.bot  = context.bot
        login_handler.bot    = context.bot
        login_handler.users_db = users_db

        crawler = WebCrawler(
            page       = page,
            gemini_model = gemini_model,
            bot        = context.bot,
            chat_id    = request["chat_id"],
            user_data  = user_data,
            users_db   = users_db,
            request_id = request_id,
        )
        active_crawlers[telegram_id] = crawler
        agent = crawler.nav_agent  # keep reference for session helpers below

        # Use the crawler to reach the actual form page
        try:
            print(f"\n[Bot] Starting WebCrawler for: {form_key}")
            found, final_url, reason = await crawler.crawl(
                url, form_key, max_depth=8
            )
        except NavigationBlockedError as nav_err:
            await context.bot.send_message(
                chat_id=request["chat_id"],
                text=(
                    "🚫 Website Access Blocked\n\n"
                    f"Reason: {nav_err}\n\n"
                    "Why this happens:\n"
                    "• Website detects automated access (anti-bot measures)\n"
                    "• CAPTCHA verification required\n"
                    "• IP address temporarily blocked\n\n"
                    "How to fix:\n"
                    "1. Visit the website manually in your browser\n"
                    "2. Complete any CAPTCHA verification\n"
                    "3. Try again in 5-10 minutes\n"
                    "4. Or try a different form"
                )
            )
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass
            del pending_requests[request_id]
            return
        except Exception as e:
            # Catch network errors like ERR_ABORTED
            error_msg = str(e)
            if "ERR_ABORTED" in error_msg or "net::" in error_msg:
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "🚫 Network Error / Website Blocked Access\n\n"
                        "The website detected automation and refused connection.\n\n"
                        "This happens with:\n"
                        "• Government sites (UPSC, SSC, Bank portals)\n"
                        "• Sites with strict anti-bot protection\n\n"
                        "Solutions:\n"
                        "1. Try accessing manually in your browser\n"
                        "2. Use a VPN or different network\n"
                        "3. Wait a few minutes and try again\n"
                        "4. Some sites may not support automation"
                    )
                )
            else:
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=f"❌ Error: {error_msg[:100]}"
                )
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass
            del pending_requests[request_id]
            return

        if not found:
            # Better error messages based on the reason
            if "login" in reason.lower():
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "🔐 Login Required\n\n"
                        f"📍 Current Page: {final_url}\n\n"
                        "The form requires you to login first.\n\n"
                        "What to do:\n"
                        "1. The browser window is open at the login page\n"
                        "2. Please login with your credentials\n"
                        "3. After logging in, navigate to the form\n"
                        "4. I'll try to detect and fill the form automatically\n"
                        "5. Or close the browser if you prefer to fill manually\n\n"
                        "⏱️ Browser will stay open for 3 minutes"
                    )
                )
                # Wait longer for user to login
                await wait_until_page_closed(page, timeout=180)
            elif "loop" in reason.lower():
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "🔄 Navigation Loop Detected\n\n"
                        f"📍 Current Page: {final_url}\n\n"
                        "The bot got stuck in a navigation loop.\n\n"
                        "This happens when:\n"
                        "• The website has complex navigation\n"
                        "• Multiple pages look similar\n"
                        "• The form requires specific steps\n\n"
                        "Solutions:\n"
                        "1. Try a more specific form request\n"
                        "2. Check if the form URL is correct\n"
                        "3. Navigate manually in the open browser\n\n"
                        "⏱️ Browser will stay open for 2 minutes"
                    )
                )
                try:
                    await wait_until_page_closed(page, timeout=120)
                except asyncio.TimeoutError:
                    pass
            elif "blocked" in reason.lower() or "captcha" in reason.lower():
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "🚫 Access Blocked / CAPTCHA Required\n\n"
                        f"📍 Current Page: {final_url}\n\n"
                        "The website is blocking automated access.\n\n"
                        "Common reasons:\n"
                        "• Anti-bot protection detected automation\n"
                        "• CAPTCHA verification required\n"
                        "• IP rate limiting\n\n"
                        "What to do:\n"
                        "1. Complete CAPTCHA in the browser window\n"
                        "2. Try again in a few minutes\n"
                        "3. Use a VPN if available\n"
                        "4. Some government sites don't allow automation\n\n"
                        "⏱️ Browser will stay open for 2 minutes"
                    )
                )
                try:
                    await wait_until_page_closed(page, timeout=120)
                except asyncio.TimeoutError:
                    pass
            elif "no navigable" in reason.lower() or "no links" in reason.lower():
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "🤷 Cannot Find Navigation Path\n\n"
                        f"📍 Current Page: {final_url}\n\n"
                        "The page doesn't have clear navigation to the form.\n\n"
                        "Possible causes:\n"
                        "• This might already be the form page (check browser)\n"
                        "• The form requires JavaScript/cookies enabled\n"
                        "• The website structure is unusual\n\n"
                        "What to do:\n"
                        "1. Check the open browser - you might already be at the form\n"
                        "2. Try clicking visible buttons/links manually\n"
                        "3. If you find the form, I'll try to detect and fill it\n\n"
                        "⏱️ Browser will stay open for 2 minutes"
                    )
                )
                try:
                    await wait_until_page_closed(page, timeout=120)
                except asyncio.TimeoutError:
                    pass
            else:
                # Generic failure message
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=(
                        "⚠️ Could Not Reach Form Automatically\n\n"
                        f"📍 Current Page: {final_url}\n"
                        f"🔍 Reason: {reason}\n\n"
                        "The AI couldn't automatically navigate to the form.\n\n"
                        "What you can do:\n"
                        "1. Browser window is open - try navigating manually\n"
                        "2. Look for buttons like 'Apply', 'Register', 'New Form'\n"
                        "3. Once you reach the form, I may auto-detect it\n"
                        "4. Close browser when done\n\n"
                        "⏱️ Browser will stay open for 2 minutes"
                    )
                )
                try:
                    await wait_until_page_closed(page, timeout=120)
                except asyncio.TimeoutError:
                    pass
            
            # Cleanup
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass
            del pending_requests[request_id]
            return

        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=(
                "✅ Successfully Reached Form Page!\n"
                f"📍 URL: {final_url}\n"
                f"🎯 Navigation: {reason}\n\n"
                "🔍 Extracting form fields..."
            ),
        )

        # We are on the form page; extract and fill
        await asyncio.sleep(2)
        fields = []
        for attempt in range(10):
            fields = await extract_form_fields(page)
            if fields:
                break
            await asyncio.sleep(1)
        
        print(f"\n📄 INITIAL: Extracted {len(fields)} fields at {page.url}")
        
        if not fields:
            await context.bot.send_message(
                chat_id=request["chat_id"],
                text=(
                    "⚠️ No form fields found on this page.\n\n"
                    "Possible reasons:\n"
                    "• The page is still loading\n"
                    "• The form requires interaction first\n"
                    "• This might not be a form page\n\n"
                    "The browser is open - try navigating to the form manually.\n"
                    "⏱️ Browser will stay open for 2 minutes."
                )
            )
            await wait_until_page_closed(page, timeout=120)
            
            # Update session with failure
            if hasattr(agent, 'current_session_steps'):
                agent.current_session_steps.append({
                    "url": final_url,
                    "action": "form_extraction_failed",
                    "details": "No fields found",
                    "timestamp": datetime.now().isoformat()
                })
                await agent._save_failed_session(url, form_key, "No form fields detected")
            
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass
            del pending_requests[request_id]
            return
        
        classified = classify_fields_with_gemini(fields, gemini_model)
        print(f"\n🤖 Classified {len(classified)} fields")
        
        # Show visual feedback during filling
        await agent.visual.show_form_found()
        
        filled_count = await autofill_form(page, classified, user_data['extracted_fields'])
        
        # Update session with success
        if hasattr(agent, 'current_session_steps'):
            agent.current_session_steps.append({
                "url": final_url,
                "action": "form_filled",
                "details": f"Filled {filled_count} fields",
                "timestamp": datetime.now().isoformat()
            })
            # Save successful session
            await agent._save_successful_session(url, form_key, final_url)
            # Update with field count
            if hasattr(agent.session_storage, 'sessions') and agent.session_storage.sessions:
                last_session = agent.session_storage.sessions[-1]
                last_session['form_filled'] = True
                last_session['fields_filled_count'] = filled_count
                agent.session_storage._save_sessions()
        
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=f"✅ Form Auto-Filled Successfully!\n"
                 f"📊 Filled {filled_count} out of {len(classified)} fields.\n\n"
                 f"👀 Please review the form carefully:\n"
                 f"• Check all filled values are correct\n"
                 f"• Fill any remaining fields manually\n"
                 f"• Click Submit when ready\n\n"
                 f"📌 The bot has learned this navigation path for next time!\n\n"
                 f"⏱️ Browser will stay open for 5 minutes."
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
    finally:
        # Cleanup active crawler tracking
        if telegram_id in active_crawlers:
            del active_crawlers[telegram_id]
            
    del pending_requests[request_id]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors and gracefully exit on conflict."""
    print(f"Update {update} caused error {context.error}")
    
    # Check if it's a conflict error (multiple instances running)
    if "Conflict" in str(context.error) or "terminated by other getUpdates" in str(context.error):
        print("\n❌ CONFLICT ERROR: Another bot instance is already running!")
        print("📍 Make sure only ONE instance of main.py is running.")
        print("🛑 Shutting down this instance...\n")
        await context.application.stop()

if __name__ == "__main__":
    # Enable concurrent handling of updates so a long-running fill does not block new messages
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("test", test_command))
    
    # Add message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Add callback query handler
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Playwright Bot with Document Processing is running...")
    print("📱 Open Telegram and send a message to your bot!")
    print("📄 Upload documents to extract user details!")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
