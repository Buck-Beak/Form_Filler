from __future__ import annotations
from typing import Tuple
from playwright.async_api import async_playwright
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
