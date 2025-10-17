import os
import json
import re
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from playwright.async_api import async_playwright

# ── Load environment variables ──
load_dotenv()
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Configure Gemini ──
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# ── Load forms DB and users DB ──
with open("forms.json", "r") as f:
    forms = json.load(f)
with open("users.json", "r") as f:
    users_db = json.load(f)

# ── Store pending autofill requests ──
pending_requests = {}

# ── Extract form fields using Playwright ──
async def extract_form_fields(page):
    """Extract input/textarea/select fields with labels"""
    js_code = """
    () => {
        const fields = [];
        const inputs = document.querySelectorAll('input, textarea, select');
        
        inputs.forEach(inp => {
            const field_id = inp.id;
            const field_name = inp.name;
            const placeholder = inp.placeholder;
            const field_type = inp.type || inp.tagName.toLowerCase();
            let label_text = '';
            
            // Try standard label lookup
            if (field_id) {
                const label = document.querySelector(`label[for="${field_id}"]`);
                if (label) label_text = label.innerText;
            }
            
            // Advanced lookup - find nearest label
            if (!label_text) {
                const parent = inp.closest('div, td, li');
                if (parent) {
                    const label = parent.querySelector('label');
                    if (label) label_text = label.innerText;
                }
            }
            
            // Fallback to aria-label or placeholder
            if (!label_text) {
                label_text = inp.getAttribute('aria-label') || 
                           inp.getAttribute('aria-placeholder') || 
                           placeholder || '';
            }
            
            // Clean up
            label_text = label_text.replace(/[*:]/g, '').trim();
            
            fields.push({
                id: field_id,
                name: field_name,
                placeholder: placeholder,
                type: field_type,
                label: label_text
            });
        });
        
        return fields;
    }
    """
    
    fields = await page.evaluate(js_code)
    return fields

# ── Classify fields using Gemini ──
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
- assessment_year
- pan
- dob
- mobile
- other

Return JSON ONLY (no markdown, no explanation), format:
[
  {{"id": "...", "name": "...", "category": "..."}},
  ...
]

Fields:
{json.dumps(fields, indent=2)}
"""
    
    response = gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    
    # Remove markdown fences
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)
    
    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini parse error:", raw_text, e)
        return []

# ── Autofill form using Playwright ──
async def autofill_form(page, classified_fields, user_data):
    """Fill form fields with user data"""
    filled_count = 0
    
    for mapping in classified_fields:
        field_id = mapping.get("id")
        field_name = mapping.get("name")
        category = mapping.get("category")
        
        # Get value from user data
        value = user_data.get(category)
        
        if not value:
            continue
        
        # Try to fill by ID first, then by name
        selector = None
        if field_id:
            selector = f"#{field_id}"
        elif field_name:
            selector = f"[name='{field_name}']"
        
        if not selector:
            continue
        
        try:
            # Wait for element and fill it with human-like behavior
            element = page.locator(selector).first
            
            # Wait a bit before interacting (more human-like)
            await asyncio.sleep(0.5)
            
            if await element.is_visible(timeout=5000):
                # Click to focus
                await element.click()
                await asyncio.sleep(0.2)
                
                # Clear and fill
                await element.clear()
                await asyncio.sleep(0.1)
                
                # Type with delays (more human-like)
                await element.type(str(value), delay=50)  # 50ms between keystrokes
                
                filled_count += 1
                print(f"✅ Filled '{category}' into {selector}")
        except Exception as e:
            print(f"⚠️ Could not fill {selector} ({category}): {e}")
    
    return filled_count

# ── Get form URL by user prompt ──
def get_form_url(prompt: str):
    prompt = prompt.lower()
    for key, info in forms.items():
        if key.lower() in prompt:
            return info["url"], key
    return None, None

# ── Telegram /start command ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Hello! I'm your **Playwright Hybrid Form-Filling Assistant Bot**.\n\n"
        "🎯 **Two modes available:**\n\n"
        "1️⃣ **Auto Mode** - Bot opens browser automatically\n"
        "2️⃣ **Manual Mode** - You open browser, bot fills it\n\n"
        "Send a message like:\n"
        "👉 `I want to fill JEE form`\n\n"
        "Choose your preferred mode when prompted! 🚀"
    )
    await update.message.reply_text(welcome_message)

# ── Handle user text messages ──
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.message.chat_id
    
    # Find matching form
    url, form_key = get_form_url(user_text)
    if not url:
        await update.message.reply_text("❌ Form not found in my database.")
        return
    
    # Find user data
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    if not user_data:
        await update.message.reply_text("❌ Your user data is not in the database.")
        return
    
    # Store pending request
    import time
    request_id = f"{telegram_id}_{int(time.time())}"
    pending_requests[request_id] = {
        "url": url,
        "form_key": form_key,
        "user_data": user_data,
        "chat_id": chat_id
    }
    
    # Create inline buttons for mode selection
    keyboard = [
        [InlineKeyboardButton("🤖 Auto Mode (Bot Opens Browser)", callback_data=f"auto_{request_id}")],
        [InlineKeyboardButton("👤 Manual Mode (I'll Open Browser)", callback_data=f"manual_{request_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 Found form: **{form_key}**\n"
        f"🌐 URL: {url}\n\n"
        f"⚠️ **Note:** Government websites often block automated browsers.\n\n"
        f"Choose your preferred mode:",
        reply_markup=reply_markup
    )

# ── Handle button clicks ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Extract mode and request ID from callback data
    callback_data = query.data
    mode, request_id = callback_data.split("_", 1)
    
    if request_id not in pending_requests:
        await query.edit_message_text("❌ Request expired or invalid.")
        return
    
    request = pending_requests[request_id]
    url = request["url"]
    user_data = request["user_data"]
    form_key = request["form_key"]
    
    if mode == "manual":
        # Manual mode - give instructions
        await query.edit_message_text(
            f"👤 **Manual Mode Selected**\n\n"
            f"📋 **Instructions:**\n"
            f"1. Open Chrome and press `Ctrl+L` to access address bar\n"
            f"2. Go to: `chrome://extensions`\n"
            f"3. Enable **Developer mode**\n"
            f"4. Start Chrome with:\n\n"
            f"```\n"
            f'chrome.exe --remote-debugging-port=9222\n'
            f"```\n\n"
            f"5. Navigate to: {url}\n"
            f"6. Reply 'ready' when form is loaded\n\n"
            f"⚠️ **Alternative:** Just open the URL normally and fill manually using your profile data."
        )
        # Store mode in request
        request["mode"] = "manual_waiting"
        return
    
    # Auto mode
    await query.edit_message_text(
        f"🔄 Opening browser and filling form for: **{form_key}**\n"
        f"Please wait..."
    )
    
    # Run Playwright to open and fill the form
    try:
        async with async_playwright() as p:
            # Launch with stealth settings
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            
            browser_context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            )
            
            page = await browser_context.new_page()
            
            # Hide automation
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Navigate
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
                
                # Check for blocks
                page_content = await page.content()
                if "permission denied" in page_content.lower() or "access denied" in page_content.lower():
                    await context.bot.send_message(
                        chat_id=request["chat_id"],
                        text=f"⚠️ **Website blocked the automated browser.**\n\n"
                             f"This is common with government websites.\n\n"
                             f"**Please open manually:** {url}"
                    )
                    await browser.close()
                    del pending_requests[request_id]
                    return
                
            except Exception as nav_error:
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=f"⚠️ Could not load: {str(nav_error)}\n\nTry manual mode instead."
                )
                await browser.close()
                del pending_requests[request_id]
                return
            
            # Extract and fill
            fields = await extract_form_fields(page)
            print(f"📄 Extracted {len(fields)} fields")
            
            classified = classify_fields_with_gemini(fields)
            print(f"🤖 Classified {len(classified)} fields")
            
            filled_count = await autofill_form(page, classified, user_data)
            
            await context.bot.send_message(
                chat_id=request["chat_id"],
                text=f"✅ Form opened and auto-filled!\n"
                     f"📊 Filled {filled_count} fields.\n\n"
                     f"👀 Review and submit. Browser stays open 2 minutes."
            )
            
            await asyncio.sleep(120)
            await browser.close()
            
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(error_msg)
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=error_msg
        )
    
    del pending_requests[request_id]

# ── Main ──
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Playwright Hybrid Bot is running...")
    print("📱 Two modes: Auto (bot opens) or Manual (you open)")
    app.run_polling()
