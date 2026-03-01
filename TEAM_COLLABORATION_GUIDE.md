# Team Collaboration & Contributor Guide 🤝

Welcome to the Form Filler project! This guide will help you set up the environment, test features locally, and contribute improvements based on real-world form challenges.

## 1. 🛠️ One-Time Setup

To get your environment exactly like the main development setup, follow these steps:

### Prerequisites
- **Python 3.10+**
- **Google Chrome** (Playwright uses it)

### Preparation
```powershell
# Clone the repository (if you haven't)
cd your-workspace-folder

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt

# Install Playwright browser engines
python -m playwright install chromium
```

### Environment Configuration (`.env`)
Create a `.env` file in the `Form_Filler` folder with these keys:
```env
GEMINI_API_KEY=your_gemini_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TWOCAPTCHA_API_KEY=your_2captcha_key_here
```

---

## 2. 🧪 Running the Local Test Lab

The **Test Website** is our "sandbox" where we simulate complex forms before trying them on real government portals.

### Step A: Start the Local Server
```powershell
cd test_website
python -m http.server 8000
```
Visit: `http://localhost:8000/` in your browser.

### Step B: Start the Bot
Open a *new* terminal window:
```powershell
cd Form_Filler
python main.py
```

---

## 3. 🚀 How to Test & Contribute

Our workflow is simple: **Identify → Mirror → Fix → Verify.**

### 1. Identify a Problem
When you find a real-world form (e.g., a Passport or Bank form) that the bot fails to fill:
- Is it a new field type? (e.g., a date picker or range slider)
- Is it a complex login? (e.g., 2FA or "Remember Me")
- Is it a CAPTCHA we don't handle?

### 2. Mirror in the Test Website
Update the `test_website/` (HTML/CSS) to include a similar complex element. This allows us to debug without making 100 requests to a live government site.

### 3. Improve the Bot
- **Classification**: Update `field_classifier.py` if the AI doesn't recognize a field.
- **Filling**: Update `form_filler.py` to add logic for new element interactions.
- **Login**: Update `login_handler.py` for smarter credential or OTP handling.

### 4. Verify & Merge
Once it works on the `test_website`, test it on the real-world site and share your changes!

---

## 4. 📂 Key Files to Know

- **`main.py`**: The entry point. Handles Telegram commands and orchestrates the crawl.
- **`crawler.py`**: The logic that "walks" through websites to find the form.
- **`login_handler.py`**: Manages credentials, "Remember Me", and OTP (2FA) flows.
- **`form_filler.py`**: Interacts with the browser to type, click, and select options.
- **`users.json`**: Where you add test data for different personas.

---

## 💡 Pro Tips
- **Watch the Browser**: The bot runs in visible mode. If it stops, read the on-screen "thoughts" (blue box) to see what it's thinking.
- **Console Logs**: Keep an eye on the terminal. We log every classification and click action.
- **Data Sync**: Always ensure your test data in `users.json` matches the fields you've added to the test website.
