import os
import json
import re
import time
import io
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import PyPDF2
from PIL import Image
import base64

# ── Load environment variables
load_dotenv()
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Initialise Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# ── Load user database
with open("users.json", "r") as f:
    users_db = json.load(f)

# ── Load forms
with open("forms.json", "r") as f:
    forms = json.load(f)

# ── Extract form fields using Selenium
# ── Extract form fields using Selenium (IMPROVED)
def extract_form_fields(driver):
    fields = []
    # Find input, textarea, and select elements
    inputs = driver.find_elements(By.XPATH, "//input | //textarea | //select")
    
    for inp in inputs:
        field_id = inp.get_attribute("id")
        field_name = inp.get_attribute("name")
        placeholder = inp.get_attribute("placeholder")
        field_type = inp.get_attribute("type")
        label_text = None
        
        # 1. Try to find the label using the standard 'for' attribute (Original method)
        if field_id:
            try:
                label_elem = driver.find_element(By.XPATH, f"//label[@for='{field_id}']")
                label_text = label_elem.text.strip()
            except:
                pass # If standard lookup fails, proceed to advanced lookup

        # 2. Advanced Lookup (for Angular/Material/Non-standard forms)
        # Look for the nearest label or text within the parent structure.
        if not label_text or not label_text.strip():
            try:
                # Look for a <label> that is a preceding sibling or within a common ancestor 
                # (e.g., within the parent <div> of the input field).
                
                # XPath to find a <label> element that is an ancestor or preceding sibling.
                # Common pattern: <div class="form-field"><label>Label Text</label><input></div>
                # We search up to the grandparent and then look for a descendant <label>.
                label_elem = inp.find_element(By.XPATH, "./ancestor::*[2]//label[string-length(normalize-space(.)) > 0]")
                label_text = label_elem.text.strip()
                
            except Exception as e:
                # Fallback: Check for an ARIA label/description which often holds the context
                aria_label = inp.get_attribute("aria-label")
                aria_placeholder = inp.get_attribute("aria-placeholder")
                
                if aria_label:
                    label_text = aria_label
                elif aria_placeholder:
                    label_text = aria_placeholder
                
                # Final Fallback: Use placeholder text if no label found
                if not label_text and placeholder:
                    label_text = placeholder
                    
        # Clean up text
        if label_text:
            # Remove asterisks/colons and strip whitespace
            label_text = label_text.replace('*', '').replace(':', '').strip()


        fields.append({
            "id": field_id,
            "name": field_name,
            "placeholder": placeholder,
            "type": field_type,
            "label": label_text
        })
    return fields

# ── Extract text from different document types
def extract_text_from_document(file_content, file_name, file_extension):
    """Extract text from various document types"""
    try:
        if file_extension.lower() == '.pdf':
            # Handle PDF files
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        
        elif file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            # Handle image files - return raw bytes for Gemini vision
            return file_content
        
        elif file_extension.lower() in ['.txt', '.doc', '.docx']:
            # Handle text files
            try:
                return file_content.decode('utf-8')
            except:
                return str(file_content)
        
        else:
            # Default: try to decode as text
            try:
                return file_content.decode('utf-8')
            except:
                return str(file_content)
                
    except Exception as e:
        print(f"Error extracting text from {file_name}: {e}")
        return str(file_content)

# ── Parse document with Gemini
def parse_document_with_gemini(document_content, file_name, is_image=False):
    """Parse uploaded document and extract user information"""
    prompt = f"""
    You are given a document: "{file_name}". Please extract personal information from this document.
    
    Extract the following information if available:
    - name (full name)
    - email
    - phone/mobile number
    - date_of_birth (dob)
    - address
    - father_name
    - mother_name
    - aadhaar_number
    - pan_number (pan)
    - assessment_year
    - gender
    - nationality
    - marital_status
    
    Return ONLY a JSON object with the extracted information. If a field is not found, don't include it in the JSON.
    Format:
    {{
        "name": "...",
        "email": "...",
        "mobile": "...",
        "dob": "...",
        "address": "...",
        "father_name": "...",
        "mother_name": "...",
        "aadhaar_number": "...",
        "pan": "...",
        "assessment_year": "...",
        "gender": "...",
        "nationality": "...",
        "marital_status": "..."
    }}
    
    Document content:
    {document_content}
    """
    
    try:
        if is_image:
            # Use Gemini's vision capabilities for images
            import google.generativeai as genai
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Create image part for Gemini
            image_part = {
                "mime_type": "image/jpeg",
                "data": document_content
            }
            
            response = model.generate_content([image_part, prompt])
        else:
            # Regular text processing
            response = gemini_model.generate_content(prompt)
        
        raw_text = response.text.strip()
        # Clean up any markdown formatting
        raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
        raw_text = re.sub(r"```$", "", raw_text)
        
        # Parse JSON
        parsed_data = json.loads(raw_text)
        return parsed_data, None
    except Exception as e:
        return None, f"Error parsing document: {str(e)}"

# ── Save user data to users.json
def save_user_data(telegram_id, parsed_data):
    """Save parsed user data to users.json"""
    try:
        # Load existing users
        if os.path.exists("users.json"):
            with open("users.json", "r") as f:
                users = json.load(f)
        else:
            users = []
        
        # Add telegram_id to parsed data
        parsed_data["telegram_id"] = telegram_id
        
        # Check if user already exists
        user_index = None
        for i, user in enumerate(users):
            if user.get("telegram_id") == telegram_id:
                user_index = i
                break
        
        if user_index is not None:
            # Update existing user
            users[user_index].update(parsed_data)
        else:
            # Add new user
            users.append(parsed_data)
        
        # Save back to file
        with open("users.json", "w") as f:
            json.dump(users, f, indent=4)
        
        return True, "User data saved successfully"
    except Exception as e:
        return False, f"Error saving user data: {str(e)}"

# ── Classify fields using Gemini
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
    - other

    Return JSON ONLY (no markdown, no explanation), format:
    [
      {{"id": "...", "category": "..."}},
      ...
    ]

    Fields:
    {fields}
    """
    print("\n🤖 HTML Fields Sent to Gemini:\n", fields)
    response = gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)
    print("Gemini response:", raw_text)
    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini parse error:", raw_text, e)
        return []

# ── Autofill form
def autofill_form(driver, classified_fields, user_data):
    # Mapping to translate Gemini's categories to your users.json keys
    KEY_MAP = {
        "date_of_birth": "dob",
        "phone": "mobile",
        # Add other common differences here if needed (e.g., "full_name": "name")
    }
    
    # Ensure all user data keys align with Gemini's categories
    # The default key is the category itself.
    
    print("\n📝 Autofilling Data:")
    print("-" * 40)
    for mapping in classified_fields:
        field_id = mapping.get("id")
        gemini_category = mapping.get("category")
        
        # Determine the key to use in the user_data dictionary
        data_key = KEY_MAP.get(gemini_category, gemini_category)
        
        # Get the value using the determined key
        value = user_data.get(data_key)

        # Print what we're about to fill
        print(f"Field ID: {field_id}, Category: {gemini_category} (Mapped to '{data_key}'), Value: {value}")

        if not value or not field_id:
            print(f"⚠️ Skipping field_id={field_id} (no value or no ID)")
            continue

        try:
            elem = driver.find_element(By.ID, field_id)
            elem.clear()
            elem.send_keys(str(value))
            print(f"✅ Filled '{gemini_category}' into field '{field_id}' with value '{value}'")
        except Exception as e:
            print(f"❌ Could not fill field '{field_id}' ({gemini_category}): {e}")
    print("-" * 40)

# ── /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm your Form-Filling Assistant Bot.\n\n"
        "📋 **How to use:**\n"
        "1️⃣ Upload your documents (PDF, images, text files) to extract your information\n"
        "2️⃣ Send me a message like 'I want to fill [form name]' to auto-fill forms\n\n"
        "📄 **Supported documents:** Aadhaar, PAN, Passport, Resume, ID cards, etc.\n"
        "🎯 **Supported forms:** JEE, NEET, Income Tax, and more!"
    )

# ── Handle document uploads
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads and parse them with Gemini"""
    document = update.message.document
    telegram_id = update.message.from_user.id
    
    await update.message.reply_text("📄 Processing your document... Please wait!")
    
    try:
        # Download the document
        file = await context.bot.get_file(document.file_id)
        
        # Read document content
        file_content = await file.download_as_bytearray()
        
        # Get file extension
        file_extension = os.path.splitext(document.file_name)[1] if document.file_name else ''
        
        # Extract text based on file type
        document_content = extract_text_from_document(file_content, document.file_name, file_extension)
        
        # Check if it's an image
        is_image = file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        
        # Parse with Gemini
        parsed_data, error = parse_document_with_gemini(document_content, document.file_name, is_image)
        
        if error:
            await update.message.reply_text(f"❌ Error parsing document: {error}")
            return
        
        if not parsed_data:
            await update.message.reply_text("❌ No information could be extracted from the document.")
            return
        
        # Save to users.json
        success, message = save_user_data(telegram_id, parsed_data)
        
        if success:
            # Show extracted information
            info_text = "✅ **Document processed successfully!**\n\n📋 **Extracted Information:**\n"
            for key, value in parsed_data.items():
                if key != "telegram_id" and value:
                    info_text += f"• **{key.replace('_', ' ').title()}:** {value}\n"
            
            await update.message.reply_text(info_text)
            await update.message.reply_text(
                "🎉 Your information has been saved! You can now use form filling commands."
            )
        else:
            await update.message.reply_text(f"❌ Error saving data: {message}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing document: {str(e)}")

# ── Handle user messages
user_sessions = {}  # Store which user is waiting to attach Chrome

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_text = update.message.text.lower()

    # If user types "done" and is waiting for Chrome
    if user_text == "done" and chat_id in user_sessions:
        await update.message.reply_text("✅ Attaching to your Chrome...")

        # Attach to Chrome using remote debugging
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Chrome(options=chrome_options)

        # Get the user data and form info from session
        session = user_sessions.pop(chat_id)
        user_data = session["user_data"]
        fields = extract_form_fields(driver)
        classified = classify_fields_with_gemini(fields)
        autofill_form(driver, classified, user_data)

        await update.message.reply_text("✅ Form auto-filled! Please review and submit manually.")
        return

    # Step 1: Match form from user text
    matched_form = None
    for form_key in forms.keys():
        if form_key.lower() in user_text:
            matched_form = form_key
            break

    if not matched_form:
        await update.message.reply_text("❌ I couldn't find that form in my list.")
        return

    # Step 2: Get form URL and user data
    form_info = forms[matched_form]
    form_url = form_info["url"]

    # Find user in users_db
    telegram_id = update.message.from_user.id
    user_data = next((u for u in users_db if u["telegram_id"] == telegram_id), None)
    if not user_data:
        await update.message.reply_text("❌ Your user data is not in the database.")
        return

    user_sessions[chat_id] = {
        "user_data": user_data,
        "form_url": form_url
    }

    await update.message.reply_text(
        f"🌐 Please open this form in your Chrome browser manually:\n\n{form_url}\n\n"
        "After opening the form, type **'done'** here to continue auto-filling."
    )

# ── Run bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running...")
    app.run_polling()
