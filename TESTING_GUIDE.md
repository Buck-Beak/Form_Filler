# Bot Testing Guide

## Start the Bot

```powershell
cd "c:\Users\abhij\OneDrive\Desktop\finalYearProject\Form_Filler"
python main.py
```

Wait for:
```
🤖 Playwright Bot with Document Processing is running...
📱 Open Telegram and send a message to your bot!
```

## Test Commands in Telegram

### 1. **Register Your Account** (First time only)
```
/myid
```
Expected: Bot shows your Telegram ID and asks to register

### 2. **Upload Document to Register**
- Upload any document (PDF, Word, Image, etc.)
- Bot extracts your personal details
- Your account is registered

### 3. **Test Dynamic URL Finding**
```
I want to fill JEE form
help me with UPSC CSE
income tax filing
passport application
show me NEET
```

Bot should respond:
- ✅ "Found matching form: jee_nta"
- ✅ "Reason: Found official form"
- ✅ Or "Searching for best matching form using AI..."

### 4. **Test Auto-Navigation**
After finding a form, click: 🚀 Open & Auto-Fill Form

Bot will:
1. Open browser
2. Navigate through website
3. Look for form page (up to 5 steps)
4. Extract form fields
5. Auto-fill with your data
6. Show filled count

### 5. **Manual Navigation Fallback**
If bot can't find form automatically:
- Browser stays open for 2 minutes
- You can manually navigate to form page
- Bot waits and closes when you close browser

## Expected Behaviors

### ✅ Good Signs
- "Form detected on page" - Found the form!
- "[NAV] Found N form-related links" - Bot is finding links
- "[NAV] AI selected link N" - AI chose which link to click
- "Filled X fields" - Successfully auto-filled

### ⚠️ Warning Signs
- "No navigable links found" - Page has no buttons/links
- "Could not automatically locate form" - Needs manual help
- "Navigation blocked" - Site has CAPTCHA/access control

## Debugging Tips

### Check Terminal Output
Look for [NAV] messages:
```
[NAV] Attempt 1 at https://www.nta.ac.in/
[NAV] Clicking index 3 text='Apply Online' href='...'
[NAV] Attempt 2 at https://...form-page
[NAV] Form found on page!
```

### If Bot Gets Stuck
1. Check if website has login requirement
2. Check if page has CAPTCHA
3. Check browser window - see if it loaded correctly
4. Try a different form first

### Enable More Logging
Edit [navigation_agent.py](navigation_agent.py) and add:
```python
print(f"[DEBUG] Page title: {await self.page.title()}")
print(f"[DEBUG] Found links: {len(links)}")
```

## Quick Test Sequence

1. Start bot: `python main.py`
2. In Telegram: `/myid`
3. Upload a document with your details
4. Send: "I want to fill JEE form"
5. Click "🚀 Open & Auto-Fill Form"
6. Watch terminal for navigation logs
7. Browser should show navigation steps

## Known Limitations

1. **Login Required Sites**: Bot can't auto-fill login forms (needs manual login first)
2. **CAPTCHA Protected**: Sites with CAPTCHA will block navigation
3. **Complex Forms**: Multi-page forms may need manual guidance
4. **Dynamic Content**: Some JavaScript-heavy sites need time to load

## Next Steps if Tests Fail

1. **Form not found?**
   - Increase `max_attempts` in navigation_agent.py (currently 5)
   - Check if website has the form you're looking for

2. **Timeout error?**
   - Site may be slow - increase timeout in navigation_agent.py
   - Try with a faster internet connection

3. **Bot doesn't click links?**
   - Website may use unusual button styles
   - Check if website blocks automation (requires proxy)

## Support Forms

These forms should work well:
- ✅ JEE (nta.ac.in)
- ✅ UPSC (upsconline.nic.in)
- ✅ Income Tax (eportal.incometax.gov.in)
- ✅ Demo forms (demoqa.com, practicetestautomation.com)

These may need help:
- ⚠️ Passport (requires login first)
- ⚠️ Bank (requires validation)
- ⚠️ Any site with CAPTCHA
