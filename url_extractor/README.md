# URL Extractor (AI-driven with Intelligent Navigation)

This module resolves the correct form URL from a free-text user request and intelligently navigates to find the actual form page using:
- Known forms lookup (uses project-level `forms.json`)
- Synonym matching
- AI intent resolution (Google Gemini)
- Web search fallback (DuckDuckGo HTML)
- **Intelligent navigation using AI guidance to find form pages**
- **404 detection and login requirement handling**
- **Manual login support with automatic continuation**
- Stealth verification using Playwright to overcome anti-bot checks

## Key Features

### 🎯 Smart Navigation
- Automatically navigates through website pages to find forms
- Uses AI (Gemini) to analyze page content and suggest next steps
- Detects and handles:
  - 404 pages (reports "Page not found")
  - Login requirements (prompts user to login when running in visible mode)
  - Access denied / blocked pages
  - CAPTCHA challenges

### 🔐 Login Handling
- Detects when login is required
- In **visible mode** (`--visible` flag): Opens browser window and waits for user to login manually
- Monitors login completion (checks every 5s for up to 3 minutes)
- Resumes navigation automatically after successful login
- Reports clear reasons when login fails or times out

### 🤖 AI-Powered Decisions
- Analyzes current page content, links, and context
- Suggests best links to click to reach form page
- Adapts navigation strategy based on page structure
- Falls back to heuristics if AI unavailable

## Files
- `config.py` — loads `.env` (GEMINI_API_KEY optional), sets default user-agent
- `normalizer.py` — text normalization and keyword extraction
- `resolvers.py` — implements the resolver pipeline and returns candidates with scores
- `verify.py` — **Enhanced with intelligent navigation, 404 detection, login handling**
- `service.py` — high-level API `resolve_form_url()` combining resolvers and navigation
- `run_demo.py` — CLI to try the resolver locally

## Setup
1. Ensure you have the project `.env` with optional `GEMINI_API_KEY` (recommended for best results).
2. Install dependencies:

```powershell
pip install -r requirements.txt
pip install beautifulsoup4 requests
```

The top-level `requirements.txt` already contains `playwright` and `google-generativeai`.

Install Playwright browsers if not already done:

```powershell
python -m playwright install chromium
```

## Try it

### Headless mode (default)
Quick automated checks, no manual login:

```powershell
python -m url_extractor.run_demo "I want to pay my income tax online"
python -m url_extractor.run_demo "help me e-verify my ITR"
python -m url_extractor.run_demo "jee main application form"
```

### Visible mode (for login-required sites)
Opens browser window so you can login manually:

```powershell
python -m url_extractor.run_demo "I want to pay my income tax online" --visible
python -m url_extractor.run_demo "income tax e-filing login" --visible
```

When running with `--visible`:
1. Browser opens and navigates to the site
2. If login is detected, you'll see: "⚠️ Login required. Please login manually in the browser..."
3. Complete the login in the browser window
4. Script automatically detects login completion and continues navigation
5. Final form page URL is returned

## What You'll See

Example output:
```
🔍 Resolving form URL for: I want to pay my income tax online
🖥️  Mode: Headless

🔍 Trying candidate: https://eportal.incometax.gov.in/... (score: 0.75)
🔍 Navigation attempt 1/3 at https://eportal.incometax.gov.in/...
🔗 AI suggests clicking: 'E-Pay Tax' - Direct link to tax payment form
✅ Found forms on page: https://eportal.incometax.gov.in/.../e-pay-tax

📊 RESULTS:
✅ Best URL: https://eportal.incometax.gov.in/.../e-pay-tax
🧭 Navigation:
   Found: True
   Final URL: https://eportal.incometax.gov.in/.../e-pay-tax
   Reason: Form found on current page
```

## Common Scenarios

### Scenario 1: Direct form page
- Candidate URL already has forms
- Navigation confirms immediately
- Returns original URL

### Scenario 2: Landing page navigation
- Initial URL is homepage or portal
- AI analyzes links and suggests "Apply" or "Form" link
- Clicks suggested link
- Finds and confirms form page

### Scenario 3: Login required
```
❌ Login required - please run with headless=False and login manually
```
**Solution:** Run with `--visible` flag

### Scenario 4: 404 or not found
```
❌ 404 - Page not found
```
Tries next candidate automatically

### Scenario 5: Access denied / CAPTCHA
```
❌ CAPTCHA detected - cannot proceed automatically
```
or
```
❌ Access denied or blocked
```
Tries next candidate or reports issue

## Integration with Main Bot

The enhanced API returns detailed navigation results:

```python
from url_extractor.service import resolve_form_url

url, meta = await resolve_form_url(
    user_text="I want to pay income tax",
    verify=True,
    navigate=True,      # Enable intelligent navigation
    headless=True,      # Set False to allow manual login
    timeout_s=20
)

if url:
    if meta.get("needs_login") and headless:
        # Prompt user: "This form requires login. Starting browser..."
        # Re-run with headless=False
        pass
    else:
        # Use url with existing Playwright bot flow
        pass
else:
    # No form found
    reason = meta.get("navigation", {}).get("reason", "Unknown")
    # Report to user
```

## API Reference

### `resolve_form_url(user_text, verify=True, navigate=True, headless=True, timeout_s=20)`

**Parameters:**
- `user_text` (str): User's natural language form request
- `verify` (bool): Whether to verify URLs with Playwright (default: True)
- `navigate` (bool): Enable intelligent navigation to find forms (default: True)
- `headless` (bool): Browser visibility; False = visible for manual login (default: True)
- `timeout_s` (int): Timeout per URL check in seconds (default: 20)

**Returns:**
- `url` (str | None): Best form URL found, or None
- `metadata` (dict): Contains:
  - `candidates`: List of all candidate URLs with scores
  - `selected`: The chosen candidate
  - `navigation`: Navigation details (found, final_url, reason, needs_login, steps)
  - `needs_login`: Boolean indicating if any candidate needed login

## Navigation Logic

1. **Initial Check:**
   - Detect 404 errors
   - Detect access denied / CAPTCHA
   - Check for login requirement

2. **If login required and visible mode:**
   - Wait for user to complete login (up to 3 minutes)
   - Monitor for login completion (password field disappears or URL changes)
   - Resume navigation after login

3. **Check for forms:**
   - Count visible input/textarea/select elements on page
   - If forms found → Success!

4. **AI Navigation (up to 3 attempts):**
   - Get AI hint with page context (title, URL, visible links)
   - AI suggests action: found / click link / login_required / not_found
   - Execute suggested action (click link, navigate to URL)
   - Repeat until form found or max attempts reached

5. **Heuristic Fallback:**
   - Search for links containing: "form", "apply", "register", "application"
   - Try first matching link

6. **Result:**
   - Return form URL if found
   - Return detailed reason if not found (404, login required, etc.)

## Troubleshooting

**Issue:** "Login required" in headless mode
**Solution:** Run with `--visible` flag to login manually

**Issue:** "Could not find form page after 3 attempts"
**Solution:** The site structure might be complex. Check candidates list for alternative URLs, or the site might require additional steps not yet implemented.

**Issue:** "CAPTCHA detected"
**Solution:** Some sites have CAPTCHA. Currently cannot bypass automatically. Consider alternative candidate URLs.

**Issue:** AI not providing hints
**Solution:** Ensure `GEMINI_API_KEY` is set in `.env`. Without it, falls back to heuristic link search.

## Future Enhancements
- Multi-step form detection (wizards, tabs)
- CAPTCHA solving integration
- Session persistence across runs
- Custom navigation rules per domain
- Screenshot capture at each step for debugging
