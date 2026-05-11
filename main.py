import json
import time
import asyncio
import os
from typing import Optional
import tempfile
import requests
import aiohttp  # async HTTP client
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN, STANDALONE_APP_BASE
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

# ── Load forms DB (user profiles come only from the standalone Electron app) ──
with open("forms.json", "r") as f:
    forms = json.load(f)
with open("official_forms_urls.json", "r") as f:
    official_urls = json.load(f)

# Empty: login_handler portal_credentials lookup is unused; credentials live in standalone profile fields.
users_db: list = []

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

def get_form_url(prompt: str):
    prompt = prompt.lower()
    for key, info in forms.items():
        if key.lower() in prompt:
            return info["url"], key
    return None, None


def normalize_standalone_user_response(body):
    """
    Standalone Electron app returns GET /user-details/:id as {"user": {...}}.
    Normalize to {"extracted_fields": {...}} for autofill (standalone app only).
    Nested user.extracted_fields overrides same-named keys from the user root.
    """
    if not body or not isinstance(body, dict):
        return None
    user_obj = body.get("user")
    if not isinstance(user_obj, dict):
        return None
    skip = frozenset(
        {
            "extracted_fields",
            "fields_count",
            "password",
            "telegram_id",
            "file_name",
        }
    )
    flat = {}
    for key, val in user_obj.items():
        if key in skip or val is None or val == "":
            continue
        flat[key] = val
    nested = user_obj.get("extracted_fields")
    if not isinstance(nested, dict):
        nested = {}
    merged = {**flat, **nested}
    return {"extracted_fields": merged}


async def fetch_standalone_user_bundle(telegram_id) -> Optional[dict]:
    """GET /user-details/:id from the Electron app; return normalized bundle or None."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{STANDALONE_APP_BASE}/user-details/{telegram_id}",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                raw = await resp.json()
                return normalize_standalone_user_response(raw)
    except Exception as e:
        print(f"⚠️ Standalone app request failed: {e}")
        return None


async def send_form_fill_history_to_standalone(
    telegram_id,
    form_name: str,
    form_url: str,
    filled_fields: int,
) -> None:
    """
    POST /form-fill on the Electron app (proxies to MongoDB /api/form-fill).
    Schema must match standalone_app backend formFillController.createFormFill.
    """
    payload = {
        "telegram_id": str(telegram_id),
        "form_name": form_name,
        "filled_fields": int(filled_fields),
        "timestamp": int(time.time()),
        "datetime": datetime.now().isoformat(),
        "form_url": form_url or "",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{STANDALONE_APP_BASE}/form-fill",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = (await resp.text())[:500]
                if resp.status in (200, 201):
                    print(f"[Standalone] Form fill history saved ({resp.status}): {body}")
                else:
                    print(
                        f"[Standalone] Form fill history failed HTTP {resp.status}: {body}"
                    )
    except Exception as e:
        print(f"[Standalone] Form fill history error: {e}")


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
    """Show user's Telegram ID and standalone app profile status"""
    telegram_id = update.message.from_user.id
    username = update.message.from_user.username or "N/A"
    first_name = update.message.from_user.first_name or ""

    bundle = await fetch_standalone_user_bundle(telegram_id)
    fields = (bundle or {}).get("extracted_fields") or {}

    if bundle is not None:
        status_msg = (
            f"✅ **Profile found in standalone app**\n\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"👤 Name: {fields.get('name', 'N/A')}\n"
            f"📧 Email: {fields.get('email', 'N/A')}\n"
            f"📱 Mobile: {fields.get('mobile', 'N/A')}\n"
            f"📊 Fields stored: {len(fields)}"
        )
    else:
        status_msg = (
            f"❌ **No profile in standalone app**\n\n"
            f"🆔 Your Telegram ID: `{telegram_id}`\n"
            f"👤 Telegram: {first_name} (@{username})\n\n"
            f"📝 Do this:\n"
            f"1. Open the **Electron desktop app** (API on port 5000).\n"
            f"2. Register there and/or **upload a document** in Telegram so data syncs to the app.\n"
            f"3. Run `/myid` again."
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

            send_res = requests.post(
                f"{STANDALONE_APP_BASE}/user-details", json=payload, timeout=15
            ).json()

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
        # Use / so the URL path does not contain "index" (dashboard heuristic in NavigationAgent)
        url = "http://127.0.0.1:8000/"
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
    
    profile = await fetch_standalone_user_bundle(telegram_id)
    if profile is None:
        await update.message.reply_text(
            "❌ **Standalone app has no profile for you.**\n\n"
            "• Start the **Electron app** (listening on port 5000).\n"
            "• Add your data there or **upload a document** in this chat first.\n"
            "• Then try again. Use /myid to check."
        )
        return

    request_id = f"{telegram_id}_{int(time.time())}"
    pending_requests[request_id] = {
        "url": url,
        "form_key": form_key,
        "chat_id": chat_id,
        "telegram_id": telegram_id,
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

    extracted_data = await fetch_standalone_user_bundle(request["telegram_id"])
    print("\n📥 STANDALONE APP (normalized):", extracted_data)

    if not extracted_data or "extracted_fields" not in extracted_data:
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=(
                "❌ **Could not load your profile from the standalone app.**\n\n"
                "Make sure the Electron app is running and try again (/myid)."
            ),
        )
        return

    user_data = {"extracted_fields": dict(extracted_data["extracted_fields"])}

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

        # Intent for navigation scoring / AI: form_key is often a label (e.g. "Local Test Website")
        nav_intent = (
            "register apply online examination JEE application admission form"
            if form_key == "Local Test Website"
            else form_key
        )
        if form_key == "Local Test Website":
            await context.bot.send_message(
                chat_id=request["chat_id"],
                text=(
                    "🧪 Local test lab\n\n"
                    "Serve the site from the project folder, then use the button:\n"
                    "`python test_site/serve.py`\n\n"
                    "The bot will crawl from the home page to the application form and auto-fill."
                ),
            )
        try:
            print(f"\n[Bot] Starting WebCrawler for: {form_key} (nav_intent={nav_intent!r})")
            found, final_url, reason = await crawler.crawl(
                url, nav_intent, max_depth=8
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

        await send_form_fill_history_to_standalone(
            request["telegram_id"],
            form_key,
            final_url,
            filled_count,
        )

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
