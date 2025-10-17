# Form_Filler

A Telegram bot that intelligently auto-fills web forms using AI classification (Gemini) and browser automation.

## 🚀 **Recommended Approach: playwright_bot.py**

**Best user experience!** Send a message to the bot → Get a clickable button → Browser opens and auto-fills instantly.

**Why it's better:**
- ✅ No manual "done" messages needed
- ✅ Bypasses bot detection (Playwright is stealthier than Selenium)
- ✅ Clean, visible browser with 2-minute review window
- ✅ Works with modern Angular/React forms

**Other approaches available:**
- `llm.py`: Selenium headless (often blocked by websites)
- `selenium_test.py`: Manual open + "done" message (poor UX)
- `lightning_test.py`: Generates JSON for manual Lightning extension import (tedious)
- `fetch_url.py`: URL finding helper
- `test.py`: Standalone test/demo
- `automate_lightning/`: Chrome native messaging experiment

This doc shows how to run each part on Windows (PowerShell).

## 1) Prerequisites
- Windows 10/11
- Google Chrome installed
- Python 3.10+
- PowerShell terminal

## 2) Setup the environment
From the `Form_Filler` folder:

```powershell
# 0) Optional: create and activate a virtualenv
python -m venv .venv; .\.venv\Scripts\Activate.ps1

# 1) Install dependencies
pip install -r requirements.txt

# 2) Install Playwright browsers (required for fetch_url.py)
python -m playwright install chromium
```

Ensure `.env` contains your secrets (already present in repo):
```
GEMINI_API_KEY=...  # required by anything using google-generativeai or google-genai
TELEGRAM_BOT_TOKEN=...  # required by Telegram bot scripts
```

## 🎯 Quick Start (Best Approach)

```powershell
# From Form_Filler folder
pip install -r requirements.txt
python -m playwright install chromium
python .\playwright_bot.py
```

Then:
1. Open Telegram and message your bot
2. Type: "I want to fill JEE form" (or any form from `forms.json`)
3. Click the **"🚀 Open & Auto-Fill Form"** button
4. Watch the magic happen! ✨

## 3) Running the scripts

### 🌟 A) **playwright_bot.py (RECOMMENDED)** + Anti-Detection
The best approach! Clean UX with Playwright browser automation and stealth mode.

```powershell
python .\playwright_bot.py
```

**How it works:**
1. Send a message to your Telegram bot: `"I want to fill JEE form"`
2. Bot responds with form details and a **"🚀 Open & Auto-Fill Form"** button
3. Click the button
4. Playwright opens a visible Chromium browser with anti-detection features, navigates to the form, extracts fields, asks Gemini to classify them, and auto-fills everything with human-like typing delays
5. You get 2 minutes to review and submit manually
6. Browser auto-closes after timeout

**Anti-Detection Features:**
- ✅ Hides `navigator.webdriver` flag
- ✅ Realistic browser fingerprint (user agent, headers, viewport)
- ✅ Human-like typing delays (50ms between keystrokes)
- ✅ Random delays between field fills
- ✅ Proper click-focus-type sequence
- ✅ Checks for "Permission Denied" errors

**Advantages:**
- No "done" messages or manual steps
- Stealthier than Selenium (bypasses most bot detection)
- Works with complex modern web forms (Angular, React)
- Visual feedback in real browser
- Automatic fallback suggestions if blocked

---

### 🎯 A.2) **playwright_hybrid_bot.py (For Strict Sites)**
When government sites like Income Tax e-Portal block automation, use this hybrid approach.

```powershell
python .\playwright_hybrid_bot.py
```

**Two modes:**
1. **Auto Mode** - Same as playwright_bot.py
2. **Manual Mode** - You open the browser, bot guides you

**When to use Manual Mode:**
- Government websites with strict security
- Sites that show "Permission Denied" even with stealth mode
- Sites requiring CAPTCHA or OTP

**Manual Mode Flow:**
1. Bot gives you the URL
2. You open it in your regular browser
3. Bot provides your user data to copy-paste manually
4. No automation = no detection

---

### B) fetch_url.py
Find official URLs or navigate to e-Pay Tax page using Playwright.

```powershell
# Runs the navigation function by default
python .\fetch_url.py
```

Notes:
- `find_base_url(query)` requires a valid `GEMINI_API_KEY` in `.env`.

---

### C) Alternative Telegram bots (Selenium-based, legacy)
**Note:** These have known limitations (detection, poor UX). Use `playwright_bot.py` instead.

- `llm.py`: Opens form URL with Selenium headless (often blocked by anti-bot systems)
- `selenium_test.py`: Requires you to open form manually, then type "done" in chat (bad UX)
- `lightning_test.py`: Generates Lightning Autofill JSON that you must manually import into the extension (tedious)

Start any one of them (only one at a time):

```powershell
# llm.py (legacy, often blocked)
python .\llm.py

# or selenium_test.py (legacy, poor UX)
python .\selenium_test.py

# or lightning_test.py (legacy, manual JSON import)
python .\lightning_test.py
```

Then open Telegram and DM your bot. Try messages like:
- "I want to fill JEE form"
- "Help me register for NEET"

Make sure the form name exists in `forms.json`. User data is pulled from `db.json` or `users.json` depending on the file.

---

### D) test.py (standalone demo)
A local test that opens a practice login page, asks Gemini to classify fields, and autofills test data.

```powershell
python .\test.py
```

This script uses the `google-genai` client instead of `google-generativeai`.

## 4) Chrome Extension + Native Host (automate_lightning/)
This is an experiment to have a Chrome Extension send the current page + desired fields to a Python native host, which returns an autofill JSON.

Files:
- `automate_lightning/background.js` – extension background script (connects to native host and fills fields)
- `automate_lightning/native_host.py` – Python native messaging host
- `automate_lightning/com.autofill.host.json` – Native messaging host manifest

Steps to run:

1. Edit the native host manifest to point to the correct Python script path and your extension id.
   - Open `automate_lightning/com.autofill.host.json` and update:
     - `path` to the full absolute path of `native_host.py`, e.g.
       `"path": "C:\\Users\\<you>\\OneDrive\\Desktop\\finalYearProject\\Form_Filler\\automate_lightning\\native_host.py"`
     - `allowed_origins` to include your extension id (set after loading the extension).

2. Register the native host with Chrome (Windows):
   - Copy the manifest to the per-user native messaging hosts folder:
     `%LOCALAPPDATA%\Google\Chrome\User Data\NativeMessagingHosts` and name it `com.autofill.host.json`.

3. Load the extension in Chrome:
   - Open `chrome://extensions`
   - Enable Developer mode
   - Click "Load unpacked" and select the `automate_lightning` folder
   - Note the Extension ID and update `allowed_origins` accordingly, then re-copy the manifest if needed.

4. Test it:
   - Open any page with a username/password input
   - Open DevTools console (to see logs)
   - The extension’s background script connects to the native host, sends a request, and fills fields based on returned selectors.

Troubleshooting:
- If connection fails, check the manifest path and that Python is accessible (try `py -3 --version`).
- Ensure Windows Defender or antivirus is not blocking the native host.
- You can run the native host from terminal to debug by piping a test message (advanced).

## 5) Data files
- `forms.json` – map of known form names to URLs
- `db.json`, `users.json` – user data used for autofill (note keys must match categories from LLM or are mapped in code)
- `autofill_*.json` – generated profiles

## 6) Common issues
- Missing env vars: ensure `.env` exists with `GEMINI_API_KEY` and `TELEGRAM_BOT_TOKEN`.
- ChromeDriver mismatch: install/update matching ChromeDriver; or use Chrome with remote debugging as in `selenium_test.py`.
- Gemini response not JSON: the scripts already strip ``` fences; if still failing, print the raw text to inspect.

---
If you want, I can wire a simple `tasks.json` to run the bots and add a one-click Playwright setup.
