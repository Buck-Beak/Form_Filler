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

# ── Extract form fields using Playwright (FIXED FOR IFRAMES) ──
async def extract_form_fields(page):
    """Extract input/textarea/select fields with labels, FROM ALL FRAMES"""
    
    js_code = """
    () => {
        const fields = [];
        const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="image"]), textarea, select');
        
        inputs.forEach(inp => {
            const field_id = inp.id || '';
            const field_name = inp.name || '';
            const placeholder = inp.placeholder || '';
            const field_type = inp.type || inp.tagName.toLowerCase();
            const formcontrolname = inp.getAttribute('formcontrolname') || '';
            const aria_label = inp.getAttribute('aria-label') || '';
            
            let label_text = '';
            
            // Try standard label lookup
            if (field_id) {
                const label = document.querySelector(`label[for="${field_id}"]`);
                if (label) label_text = label.innerText;
            }
            
            // Advanced lookup - find nearest label
            if (!label_text) {
                const parent = inp.closest('div, td, li, mat-form-field');
                if (parent) {
                    const label = parent.querySelector('label, mat-label');
                    if (label) label_text = label.innerText;
                }
            }
            
            // Fallback to aria-label or placeholder
            if (!label_text) {
                label_text = aria_label || placeholder || '';
            }
            
            // Clean up
            label_text = label_text.replace(/[*:]/g, '').trim();
            
            // Only include visible, non-image inputs
            const rect = inp.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0;
            
            if (isVisible) {
                fields.push({
                    id: field_id,
                    name: field_name,
                    placeholder: placeholder,
                    type: field_type,
                    label: label_text,
                    formcontrolname: formcontrolname,
                    aria_label: aria_label
                });
            }
        });
        return fields;
    }
    """
    
    all_fields = []
    
    # Extract from main page
    try:
        main_fields = await page.evaluate(js_code)
        for f in main_fields:
            f['frame'] = 'main'
        all_fields.extend(main_fields)
        print(f"  → Main page: {len(main_fields)} fields")
    except Exception as e:
        print(f"⚠️ Main page extraction failed: {e}")
    
    # Extract from ALL frames (iframes)
    for frame in page.frames:
        if frame == page.main_frame:
            continue  # Already did main
        try:
            frame_fields = await frame.evaluate(js_code)
            for f in frame_fields:
                f['frame'] = frame.url or frame.name or 'unnamed_frame'
            all_fields.extend(frame_fields)
            if frame_fields:
                print(f"  → Frame {frame.url or frame.name}: {len(frame_fields)} fields")
        except Exception as e:
            print(f"⚠️ Frame {frame.url} extraction failed: {e}")
    
    return all_fields

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
    """Fill form fields with user data (SUPPORTS IFRAMES)"""
    filled_count = 0

    # Map Gemini categories -> your users.json keys
    KEY_MAP = {
        "date_of_birth": "dob",
        "dob": "dob",
        "phone": "mobile",
        "mobile": "mobile",
        "pan": "panAdhaarUserId",
        "aadhaar_number": "panAdhaarUserId",
        "aadhaar": "panAdhaarUserId",
    }

    for mapping in classified_fields:
        field_id = mapping.get("id")
        field_name = mapping.get("name")
        category = mapping.get("category")
        field_frame = mapping.get("frame", "main")

        # Resolve user data value with KEY_MAP
        data_key = KEY_MAP.get(category, category)
        value = user_data.get(data_key)

        if not value:
            print(f"↪ Skip: no user value for category='{category}' (mapped key='{data_key}')")
            continue

        # Build candidate selectors
        candidates = []
        if field_id:
            candidates.append(f"#{field_id}")
        if field_name:
            candidates.append(f"[name='{field_name}']")
        if mapping.get("formcontrolname"):
            candidates.append(f"[formcontrolname='{mapping['formcontrolname']}']")
        if mapping.get("placeholder"):
            candidates.append(f"[placeholder='{mapping['placeholder']}']")
        if mapping.get("aria_label"):
            candidates.append(f"[aria-label='{mapping['aria_label']}']")

        if not candidates:
            print(f"↪ Skip: no selector candidates for category='{category}'")
            continue

        # Find the correct frame
        target_frame = page.main_frame
        if field_frame != "main":
            for frame in page.frames:
                if frame.url == field_frame or frame.name == field_frame:
                    target_frame = frame
                    break

        # Try each selector
        filled_this = False
        for selector in candidates:
            try:
                element = target_frame.locator(selector).first
                await asyncio.sleep(0.2)
                if not await element.count():
                    continue
                if not await element.is_visible():
                    continue

                # Focus and clear
                await element.click()
                await asyncio.sleep(0.1)
                
                try:
                    await element.clear()
                except Exception:
                    await element.fill("")

                await asyncio.sleep(0.1)
                await element.type(str(value), delay=50)
                filled_count += 1
                filled_this = True
                print(f"✅ Filled '{category}' (mapped '{data_key}') via {selector} in frame {field_frame}")
                break
            except Exception as e:
                print(f"⚠️ Try selector failed for '{category}' via {selector}: {e}")

        if not filled_this:
            print(f"❌ Could not fill '{category}' (mapped '{data_key}') — no selector matched")

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
        f"🔄 Opening browser for: **{form_key}**\n"
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
                print(f"🌐 Navigating to: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for Angular to initialize (check for common Angular markers)
                print("⏳ Waiting for Angular app to load...")
                await asyncio.sleep(5)  # Give Angular time to bootstrap
                
                # Try to wait for common Angular root elements
                try:
                    await page.wait_for_selector('app-root, [ng-app], [ng-version]', timeout=10000)
                    print("✅ Angular app detected")
                except:
                    print("⚠️ No Angular root found, continuing anyway")
                
                # Wait for network to be idle (all API calls done)
                try:
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    print("✅ Network idle")
                except:
                    print("⚠️ Network still active, continuing anyway")
                
                # Additional wait for lazy-loaded components
                await asyncio.sleep(3)
                
                print(f"📄 Total frames on page: {len(page.frames)}")
                
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
            
            print(f"\n📄 INITIAL: Extracted {len(fields)} fields")
            print("=" * 60)
            for i, field in enumerate(fields, 1):
                print(f"Field {i}:")
                print(f"  ID: {field.get('id')}")
                print(f"  Name: {field.get('name')}")
                print(f"  Type: {field.get('type')}")
                print(f"  Label: {field.get('label')}")
                print(f"  Placeholder: {field.get('placeholder')}")
                print(f"  Frame: {field.get('frame')}")
                print("-" * 40)
            print("=" * 60)
            
            # Detect if this is a login page
            login_keywords = ['password', 'username', 'user id', 'login', 'signin', 'sign in', 'email']
            has_login_field = False
            
            if fields:
                classified = classify_fields_with_gemini(fields)
                print(f"\n🤖 Classified {len(classified)} fields")
                print("Classified fields:", json.dumps(classified, indent=2))
                
                # Check if any field is login-related
                for field_data in classified:
                    category = field_data.get('category', '').lower()
                    if category in ['password', 'email'] or 'password' in category or 'email' in category:
                        has_login_field = True
                        break
                
                # Also check labels/placeholders
                if not has_login_field:
                    for field in fields:
                        label = field.get('label', '').lower()
                        placeholder = field.get('placeholder', '').lower()
                        field_type = field.get('type', '').lower()
                        
                        if field_type == 'password':
                            has_login_field = True
                            break
                        
                        for keyword in login_keywords:
                            if keyword in label or keyword in placeholder:
                                has_login_field = True
                                break
                        
                        if has_login_field:
                            break
            
            # If login page detected, notify user and wait
            if has_login_field:
                print("🔐 Login page detected! Waiting for user to log in...")
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text="🔐 **Login Required**\n\n"
                         "The browser has opened to a login page.\n"
                         "Please log in manually in the browser window.\n\n"
                         "⏳ The bot will wait up to **3 minutes** for you to log in.\n"
                         "After login, the form will be auto-filled automatically!"
                )
                
                # Wait for navigation (login redirect) or form fields to appear
                login_timeout = 180  # 3 minutes
                start_time = asyncio.get_event_loop().time()
                form_detected = False
                
                while (asyncio.get_event_loop().time() - start_time) < login_timeout:
                    await asyncio.sleep(2)
                    
                    # Check for new fields (form fields appear after login)
                    current_fields = await extract_form_fields(page)
                    
                    if current_fields:
                        # Check if these are different from login fields
                        classified_current = classify_fields_with_gemini(current_fields)
                        has_form_fields = False
                        
                        for field_data in classified_current:
                            category = field_data.get('category', '').lower()
                            # Check for form fields (not login fields)
                            if category not in ['password', 'email', 'other'] and category != '':
                                has_form_fields = True
                                break
                        
                        if has_form_fields:
                            print("✅ Form fields detected after login!")
                            form_detected = True
                            fields = current_fields
                            break
                
                if not form_detected:
                    await context.bot.send_message(
                        chat_id=request["chat_id"],
                        text="⏰ Login timeout (3 minutes). Please try again.\n"
                             "The browser will remain open for you to complete manually."
                    )
                    await asyncio.sleep(300)  # Keep browser open
                    await browser.close()
                    del pending_requests[request_id]
                    return
                
                # Re-extract and classify after login
                for attempt in range(10):
                    fields = await extract_form_fields(page)
                    if fields:
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
                    print(f"  Frame: {field.get('frame')}")
                    print("-" * 40)
                print("=" * 60)
            
            # If no fields found, try waiting longer
            if not fields:
                await asyncio.sleep(2)
                for attempt in range(10):
                    fields = await extract_form_fields(page)
                    if fields:
                        break
                    await asyncio.sleep(1)
                print(f"\n📄 FINAL CHECK: Extracted {len(fields)} fields")
                print("=" * 60)
                for i, field in enumerate(fields, 1):
                    print(f"Field {i}:")
                    print(f"  ID: {field.get('id')}")
                    print(f"  Name: {field.get('name')}")
                    print(f"  Type: {field.get('type')}")
                    print(f"  Label: {field.get('label')}")
                    print(f"  Placeholder: {field.get('placeholder')}")
                    print(f"  Frame: {field.get('frame')}")
                    print("-" * 40)
                print("=" * 60)

            # If no fields found, log HTML for debugging
            if not fields:
                html = await page.content()
                with open("debug_last_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                await context.bot.send_message(
                    chat_id=request["chat_id"],
                    text="⚠️ No form fields detected! Saved page HTML to debug_last_page.html.\n"
                         "If the form loads after a button click or login, please specify the selector or steps.\n\n"
                         "Browser will remain open for 5 minutes for manual completion."
                )
                await asyncio.sleep(300)
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
                text=f"✅ Form auto-filled!\n"
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
