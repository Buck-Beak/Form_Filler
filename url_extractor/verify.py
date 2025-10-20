from __future__ import annotations
import asyncio
import json
import re
from typing import Tuple, Dict, Any, Optional
from playwright.async_api import async_playwright, Page

try:
    import google.generativeai as genai
    from .config import GEMINI_API_KEY
except Exception:
    genai = None
    GEMINI_API_KEY = None

from .config import DEFAULT_USER_AGENT

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
"""


async def launch_stealth_context(headless: bool = True):
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process'
        ]
    )
    context = await browser.new_context(
        viewport={'width': 1366, 'height': 768},
        user_agent=DEFAULT_USER_AGENT,
        locale='en-US',
        timezone_id='Asia/Kolkata',
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
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
    page = await context.new_page()
    await page.add_init_script(STEALTH_SCRIPT)
    return p, browser, context, page


async def has_forms_on_page(page: Page) -> bool:
    """Check if page has visible form fields."""
    try:
        count = await page.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="image"]), textarea, select');
                let visible = 0;
                inputs.forEach(inp => {
                    const rect = inp.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) visible++;
                });
                return visible;
            }
        """)
        return count > 0
    except Exception:
        return False


async def detect_404(page: Page) -> bool:
    """Detect 404 or not found pages."""
    try:
        title = (await page.title()).lower()
        content = (await page.content())[:3000].lower()
        if '404' in title or 'not found' in title:
            return True
        if '404' in content and ('not found' in content or 'page not found' in content):
            return True
        return False
    except Exception:
        return False


async def detect_login_required(page: Page) -> bool:
    """Detect if page requires login."""
    try:
        content = (await page.content())[:5000].lower()
        keywords = ['login', 'sign in', 'log in', 'authenticate', 'enter password', 'username']
        # Check for login forms
        login_count = sum(1 for kw in keywords if kw in content)
        if login_count >= 2:
            # Check if there are password fields
            has_password = await page.evaluate("""
                () => {
                    const pwds = document.querySelectorAll('input[type="password"]');
                    return pwds.length > 0;
                }
            """)
            if has_password:
                return True
        return False
    except Exception:
        return False


async def get_navigation_hint_from_ai(page: Page, user_request: str, attempt: int) -> Optional[Dict[str, Any]]:
    """Ask Gemini for navigation guidance to find the form."""
    if not genai or not GEMINI_API_KEY:
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Get page context
        title = await page.title()
        url = page.url
        # Get visible links
        links = await page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                return anchors.slice(0, 30).map(a => ({
                    text: a.innerText.trim().substring(0, 100),
                    href: a.href
                })).filter(l => l.text);
            }
        """)
        
        prompt = f"""
You are helping navigate a website to find a form page.
User wants: {user_request}
Current page title: {title}
Current URL: {url}
Attempt: {attempt}/3

Visible links on page (sample):
{json.dumps(links[:20], indent=2)}

Task: Determine the best action to find the form page.
Options:
1. If current page has the form, respond: {{"action": "found", "reason": "form is here"}}
2. If you see a link that likely leads to the form, respond: {{"action": "click", "link_text": "exact text", "href": "url", "reason": "why this link"}}
3. If page requires login first, respond: {{"action": "login_required", "reason": "why"}}
4. If no relevant links, respond: {{"action": "not_found", "reason": "why"}}

Respond ONLY with valid JSON, no markdown.
"""
        
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text)
        data = json.loads(text)
        return data
    except Exception as e:
        print(f"AI navigation hint failed: {e}")
        return None


async def navigate_to_form(page: Page, user_request: str, max_attempts: int = 3, headless: bool = True) -> Tuple[bool, str, str]:
    """
    Intelligently navigate to find the form page.
    Returns (found, final_url, reason).
    If login required and headless=False, will wait for user to login.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"🔍 Navigation attempt {attempt}/{max_attempts} at {page.url}")
        
        # Wait for page to stabilize
        await asyncio.sleep(2)
        
        # Check for 404
        if await detect_404(page):
            return False, page.url, "404 - Page not found"
        
        # Check for blocking/captcha
        content_sample = (await page.content())[:5000].lower()
        if 'access denied' in content_sample or 'permission denied' in content_sample:
            return False, page.url, "Access denied or blocked"
        if 'captcha' in content_sample:
            return False, page.url, "CAPTCHA detected - cannot proceed automatically"
        
        # Check if login required
        if await detect_login_required(page):
            if headless:
                return False, page.url, "Login required - please run with headless=False and login manually"
            else:
                print("⚠️ Login required. Please login manually in the browser...")
                print("⏳ Waiting for login (checking every 5s for up to 3 minutes)...")
                # Wait for login - check if password field disappears or URL changes
                start_url = page.url
                for _ in range(36):  # 3 minutes
                    await asyncio.sleep(5)
                    still_login = await detect_login_required(page)
                    if not still_login or page.url != start_url:
                        print("✅ Login detected, continuing navigation...")
                        break
                else:
                    return False, page.url, "Login timeout - user did not complete login in 3 minutes"
        
        # Check if current page has forms
        if await has_forms_on_page(page):
            print(f"✅ Found forms on page: {page.url}")
            return True, page.url, "Form found on current page"
        
        # Ask AI for navigation hint
        hint = await get_navigation_hint_from_ai(page, user_request, attempt)
        if hint:
            action = hint.get("action")
            reason = hint.get("reason", "")
            
            if action == "found":
                # AI thinks form is here, double-check
                if await has_forms_on_page(page):
                    return True, page.url, f"AI confirmed: {reason}"
                else:
                    print(f"⚠️ AI said form found but no forms detected, continuing...")
            
            elif action == "click":
                link_text = hint.get("link_text")
                href = hint.get("href")
                print(f"🔗 AI suggests clicking: '{link_text}' ({href}) - {reason}")
                try:
                    # Try to click the link
                    # First try by text
                    if link_text:
                        try:
                            await page.click(f'text="{link_text}"', timeout=5000)
                            await page.wait_for_load_state('domcontentloaded', timeout=15000)
                            continue
                        except Exception:
                            pass
                    # Try by href
                    if href:
                        try:
                            await page.goto(href, wait_until='domcontentloaded', timeout=15000)
                            continue
                        except Exception:
                            pass
                    print("⚠️ Could not click suggested link, trying next...")
                except Exception as e:
                    print(f"⚠️ Click failed: {e}")
            
            elif action == "login_required":
                if headless:
                    return False, page.url, f"Login required: {reason}"
                else:
                    print(f"⚠️ AI detected login requirement: {reason}")
                    # Will be caught in next iteration
            
            elif action == "not_found":
                return False, page.url, f"Form page not found: {reason}"
        
        # If AI didn't help, try heuristic link search
        try:
            form_links = await page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    return anchors.map(a => ({
                        text: a.innerText.trim().toLowerCase(),
                        href: a.href
                    })).filter(l => 
                        l.text.includes('form') || 
                        l.text.includes('apply') || 
                        l.text.includes('register') ||
                        l.text.includes('application')
                    ).slice(0, 5);
                }
            """)
            if form_links:
                first = form_links[0]
                print(f"🔗 Heuristic: trying link '{first['text']}' -> {first['href']}")
                await page.goto(first['href'], wait_until='domcontentloaded', timeout=15000)
                continue
        except Exception:
            pass
        
        # No progress, break
        break
    
    # Final check
    if await has_forms_on_page(page):
        return True, page.url, "Form found after navigation"
    
    return False, page.url, f"Could not find form page after {max_attempts} attempts"


async def verify_url(url: str, timeout_ms: int = 20000) -> Tuple[bool, str]:
    """Try to open the URL with stealth Playwright. Returns (ok, reason)."""
    p = browser = context = page = None
    try:
        p, browser, context, page = await launch_stealth_context(headless=True)
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
        # basic checks: status like blocking pages often redirect; we can inspect title
        title = await page.title()
        if not title:
            return False, 'no title'
        # heuristic: permissions/denied words
        content = (await page.content())[:5000].lower()
        if 'access denied' in content or 'permission denied' in content or 'captcha' in content:
            return False, 'blocked or captcha'
        return True, 'ok'
    except Exception as e:
        return False, f'error: {e}'
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            if p:
                await p.stop()
        except Exception:
            pass


async def verify_and_navigate_to_form(url: str, user_request: str, headless: bool = True, timeout_ms: int = 20000) -> Dict[str, Any]:
    """
    Advanced verification: navigate to URL and intelligently find the form page.
    Returns dict with: found, final_url, reason, needs_login, steps
    """
    p = browser = context = page = None
    result = {
        "found": False,
        "final_url": url,
        "reason": "unknown",
        "needs_login": False,
        "steps": []
    }
    
    try:
        p, browser, context, page = await launch_stealth_context(headless=headless)
        
        # Initial navigation
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
            result["steps"].append(f"Opened {url}")
        except Exception as e:
            result["reason"] = f"Failed to open URL: {e}"
            return result
        
        # Check for immediate 404
        if await detect_404(page):
            result["reason"] = "404 - Page not found"
            result["final_url"] = page.url
            return result
        
        # Navigate to find form
        found, final_url, reason = await navigate_to_form(page, user_request, max_attempts=3, headless=headless)
        result["found"] = found
        result["final_url"] = final_url
        result["reason"] = reason
        result["needs_login"] = "login required" in reason.lower()
        
        return result
        
    except Exception as e:
        result["reason"] = f"Error during navigation: {e}"
        return result
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            if p:
                await p.stop()
        except Exception:
            pass
