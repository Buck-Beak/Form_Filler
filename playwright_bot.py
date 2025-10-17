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
    fields = []
    
    # JavaScript to extract field info
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
        "👋 Hello! I'm your **Playwright Form-Filling Assistant Bot**.\n\n"
        "Send a message like:\n"
        "👉 `I want to fill JEE form`\n"
        "👉 `Help me with Income Tax e-Pay`\n\n"
        "I'll send you a button to auto-fill the form instantly! 🚀"
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
    
    # Create inline button
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

# ── Handle button clicks ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Extract request ID from callback data
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
        f"🔄 Opening browser and filling form for: **{form_key}**\n"
        f"Please wait..."
    )
    
    # Run Playwright to open and fill the form
    try:
        async with async_playwright() as p:
            # Launch with stealth settings to avoid bot detection
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            # Create context with realistic browser fingerprint
            browser_context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='Asia/Kolkata',
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }
            )
            
            page = await browser_context.new_page()
            
            # Inject scripts to hide automation flags
            await page.add_init_script("""
                // Override the navigator.webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override the Permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Add chrome object
                window.chrome = {
                    runtime: {}
                };
                
                // Override plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)
            
            # Navigate to form with retry logic
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # Wait a bit more for dynamic content to load
                await asyncio.sleep(3)
                
                # Check for permission denied or error messages
                page_content = await page.content()
                if "permission denied" in page_content.lower() or "access denied" in page_content.lower():
                    await context.bot.send_message(
                        chat_id=request["chat_id"],
                        text="⚠️ Website blocked the automated browser. This happens with government websites.\n\n"
                             "**Workaround:** Try opening the form manually in your regular browser:\n"
                             f"{url}\n\n"
                             "Then use the form data from your profile to fill it."
                    )
                    await browser.close()
                    del pending_requests[request_id]
                    return
                
            except Exception as nav_error:
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text=f"⚠️ Could not load the page: {str(nav_error)}\n\n"
                         f"The website might have strict bot protection. Try opening it manually:\n{url}"
                )
                await browser.close()
                del pending_requests[request_id]
                return
            
            # Extract fields (wait for dynamic content)
            for attempt in range(10):
                fields = await extract_form_fields(page)
                if fields:
                    break
                await asyncio.sleep(1)  # Wait 1s and retry
            print(f"\n📄 PRE-LOGIN: Extracted {len(fields)} fields")
            print("=" * 60)
            for i, field in enumerate(fields, 1):
                print(f"Field {i}:")
                print(f"  ID: {field.get('id')}")
                print(f"  Name: {field.get('name')}")
                print(f"  Type: {field.get('type')}")
                print(f"  Label: {field.get('label')}")
                print(f"  Placeholder: {field.get('placeholder')}")
                print("-" * 40)
            print("=" * 60)
            
            # If fields are found before login, fill them immediately
            filled_count = 0
            if fields:
                classified = classify_fields_with_gemini(fields)
                print(f"\n🤖 PRE-LOGIN: Classified {len(classified)} fields")
                print("Classified fields:", json.dumps(classified, indent=2))
                filled_count = await autofill_form(page, classified, user_data)
                print(f"✅ Pre-login: filled {filled_count} fields\n")
            
            # Try to click a login button if present
            login_clicked = False
            login_selectors = [
                "button:has-text('Login')",
                "button:has-text('Sign In')",
                "a:has-text('Login')",
                "a:has-text('Sign In')",
                "input[type=submit][value*='Login']",
                "input[type=submit][value*='Sign In']",
                "button[type=submit]:has-text('Login')",
                "button[type=submit]:has-text('Sign In')"
            ]
            for sel in login_selectors:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        await asyncio.sleep(3)  # Wait for navigation or form to appear
                        login_clicked = True
                        print(f"✅ Clicked login button: {sel}")
                        break
                except Exception as e:
                    print(f"Login button check failed: {e}")

            # If login was clicked, re-scan for form fields and fill them
            if login_clicked:
                for attempt in range(10):
                    new_fields = await extract_form_fields(page)
                    if new_fields:
                        fields = new_fields
                        break
                    await asyncio.sleep(1)
                print(f"\n📄 POST-LOGIN: Extracted {len(fields)} fields")
                print("=" * 60)
                for i, field in enumerate(fields, 1):
                    print(f"Field {i}:")
                    print(f"  ID: {field.get('id')}")
                    print(f"  Name: {field.get('name')}")
                    print(f"  Type: {field.get('type')}")
                    print(f"  Label: {field.get('label')}")
                    print(f"  Placeholder: {field.get('placeholder')}")
                    print("-" * 40)
                print("=" * 60)
                
                if fields:
                    classified = classify_fields_with_gemini(fields)
                    print(f"\n🤖 POST-LOGIN: Classified {len(classified)} fields")
                    print("Classified fields:", json.dumps(classified, indent=2))
                    filled_count = await autofill_form(page, classified, user_data)
                    print(f"✅ Post-login: filled {filled_count} fields\n")

            # If still no fields, try after navigation (page reload)
            if not fields:
                await asyncio.sleep(2)
                for attempt in range(10):
                    fields = await extract_form_fields(page)
                    if fields:
                        break
                    await asyncio.sleep(1)
                print(f"\n📄 POST-NAVIGATION: Extracted {len(fields)} fields")
                print("=" * 60)
                for i, field in enumerate(fields, 1):
                    print(f"Field {i}:")
                    print(f"  ID: {field.get('id')}")
                    print(f"  Name: {field.get('name')}")
                    print(f"  Type: {field.get('type')}")
                    print(f"  Label: {field.get('label')}")
                    print(f"  Placeholder: {field.get('placeholder')}")
                    print("-" * 40)
                print("=" * 60)
                
                if fields:
                    classified = classify_fields_with_gemini(fields)
                    print(f"\n🤖 POST-NAVIGATION: Classified {len(classified)} fields")
                    print("Classified fields:", json.dumps(classified, indent=2))
                    filled_count = await autofill_form(page, classified, user_data)
                    print(f"✅ Post-nav: filled {filled_count} fields\n")

            # If no fields found, log HTML for debugging
            if not fields:
                html = await page.content()
                with open("debug_last_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text="⚠️ No form fields detected! Saved page HTML to debug_last_page.html.\n"
                         "If the form loads after a button click or login, please specify the selector or steps."
                )
                await browser.close()
                del pending_requests[request_id]
                return
            
            # Classify with Gemini
            classified = classify_fields_with_gemini(fields)
            print(f"🤖 Classified {len(classified)} fields")
            
            # Autofill
            filled_count = await autofill_form(page, classified, user_data)
            
            # Send success message
            await context.bot.send_message(
                chat_id=request["chat_id"],
                text=f"✅ Form opened and auto-filled!\n"
                     f"📊 Filled {filled_count} fields.\n\n"
                     f"👀 Please review the form in the browser and submit manually.\n"
                     f"The browser will stay open for 5 minutes."
            )
            
            # Keep browser open for user to review
            await asyncio.sleep(300)  # 5 minutes
            
            await browser.close()
            
    except Exception as e:
        error_msg = f"❌ Error filling form: {str(e)}"
        print(error_msg)
        await context.bot.send_message(
            chat_id=request["chat_id"],
            text=error_msg
        )
    
    # Clean up
    del pending_requests[request_id]

# ── Main ──
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Playwright Bot is running...")
    print("📱 Open Telegram and send a message to your bot!")
    app.run_polling()
