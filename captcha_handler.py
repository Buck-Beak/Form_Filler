"""
captcha_handler.py
~~~~~~~~~~~~~~~~~~
Detects and resolves CAPTCHAs encountered during automated navigation.

Detection supports:
  - reCAPTCHA v2 / v3  (via data-sitekey attribute)
  - hCaptcha
  - Cloudflare Turnstile
  - Generic image / text CAPTCHA (keyword scan)

Resolution pipeline (in order):
  1. Auto-solve via 2captcha API  (requires TWOCAPTCHA_API_KEY in .env)
  2. Manual Telegram fallback     (screenshot → user presses ✅ Done button)
"""

import asyncio
import os
from typing import Any, Dict, Optional

from playwright.async_api import Page


# ─────────────────────────────────────────────────────────────────────────────
# CAPTCHA type constants
# ─────────────────────────────────────────────────────────────────────────────

class CaptchaType:
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA     = "hcaptcha"
    TURNSTILE    = "turnstile"
    IMAGE        = "image"
    NONE         = "none"


# ─────────────────────────────────────────────────────────────────────────────
# CaptchaHandler
# ─────────────────────────────────────────────────────────────────────────────

class CaptchaHandler:
    """
    Usage
    -----
    handler = CaptchaHandler(bot=telegram_bot_instance)
    resolved = await handler.handle_captcha(page, chat_id=12345, request_id="req_1")
    """

    def __init__(self, bot=None, api_key: Optional[str] = None):
        """
        Parameters
        ----------
        bot      : telegram.Bot instance (optional) — needed for manual fallback
        api_key  : 2captcha API key (optional) — falls back to TWOCAPTCHA_API_KEY env var
        """
        self.bot = bot
        self.api_key = api_key or os.getenv("TWOCAPTCHA_API_KEY", "").strip()
        # chat_id (str) -> asyncio.Event, set when user presses ✅ Done
        self._pending_manual: Dict[str, asyncio.Event] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Detection
    # ─────────────────────────────────────────────────────────────────────────

    async def detect_captcha(self, page: Page) -> Dict[str, Any]:
        """
        Scan the current page for a CAPTCHA widget.

        Returns a dict:
            { "type": CaptchaType.*, "sitekey": "<string or empty>" }
        """
        try:
            result = await page.evaluate("""
                () => {
                    // ── reCAPTCHA v2 / v3 ──────────────────────────────────
                    const recaptchaEl = document.querySelector(
                        '.g-recaptcha, [data-sitekey], iframe[src*="recaptcha"]'
                    );
                    if (recaptchaEl) {
                        const sitekey = recaptchaEl.getAttribute('data-sitekey') || '';
                        const scriptV3 = document.querySelector(
                            'script[src*="recaptcha/api.js?render"]'
                        );
                        return {
                            type: scriptV3 ? 'recaptcha_v3' : 'recaptcha_v2',
                            sitekey
                        };
                    }

                    // ── hCaptcha ────────────────────────────────────────────
                    const hcaptchaEl = document.querySelector(
                        '.h-captcha, [data-hcaptcha-widget-id], iframe[src*="hcaptcha"]'
                    );
                    if (hcaptchaEl) {
                        return {
                            type: 'hcaptcha',
                            sitekey: hcaptchaEl.getAttribute('data-sitekey') || ''
                        };
                    }

                    // ── Cloudflare Turnstile ────────────────────────────────
                    const turnstileEl = document.querySelector(
                        '.cf-turnstile, [data-cf-sitekey], iframe[src*="challenges.cloudflare.com"]'
                    );
                    if (turnstileEl) {
                        return {
                            type: 'turnstile',
                            sitekey: (
                                turnstileEl.getAttribute('data-sitekey') ||
                                turnstileEl.getAttribute('data-cf-sitekey') ||
                                ''
                            )
                        };
                    }

                    // ── Generic image / text CAPTCHA ────────────────────────
                    const bodyText = (document.body && document.body.innerText || '').toLowerCase();
                    const captchaMarkers = [
                        'verify you are human', "i'm not a robot",
                        'i am not a robot', 'security check', 'prove you are human'
                    ];
                    
                    // Check for markers first
                    let hasMarker = captchaMarkers.some(m => bodyText.includes(m));
                    
                    // Specific check for 'captcha' keyword - ignore if it's just 'test captcha' or in a link
                    if (!hasMarker && bodyText.includes('captcha')) {
                        const isTestPage = bodyText.includes('testbed') || bodyText.includes('bot test');
                        const captchaElements = Array.from(document.querySelectorAll('a, button, h1, h2, h3'))
                            .filter(el => el.innerText.toLowerCase().includes('captcha'));
                        
                        // If 'captcha' only appears in links/headers on a test page, it's likely not a challenge
                        if (!(isTestPage && captchaElements.length > 0)) {
                            hasMarker = true;
                        }
                    }

                    if (hasMarker) {
                        return { type: 'image', sitekey: '' };
                    }

                    return { type: 'none', sitekey: '' };
                }
            """)
            return result or {"type": CaptchaType.NONE, "sitekey": ""}
        except Exception as e:
            print(f"[CAPTCHA] Detection error: {e}")
            return {"type": CaptchaType.NONE, "sitekey": ""}

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Auto-solve via 2captcha
    # ─────────────────────────────────────────────────────────────────────────

    async def auto_solve(self, page: Page, captcha_info: Dict[str, Any]) -> bool:
        """
        Use the 2captcha paid API to solve the CAPTCHA and inject the token.
        Returns True if solved successfully, False otherwise.
        """
        if not self.api_key:
            print("[CAPTCHA] No 2captcha API key — skipping auto-solve")
            return False

        captcha_type = captcha_info.get("type", CaptchaType.NONE)
        sitekey      = captcha_info.get("sitekey", "")

        try:
            from twocaptcha import AsyncTwoCaptcha  # type: ignore
        except ImportError:
            print("[CAPTCHA] 2captcha-python not installed — run: pip install 2captcha-python")
            return False

        solver = AsyncTwoCaptcha(self.api_key)
        print(f"[CAPTCHA] 🔑 Auto-solving '{captcha_type}' via 2captcha…")

        try:
            if captcha_type == CaptchaType.RECAPTCHA_V2:
                result = await solver.recaptcha(sitekey=sitekey, url=page.url)
                token  = result["code"]
                await page.evaluate(f"""
                    (token) => {{
                        const resp = document.getElementById('g-recaptcha-response');
                        if (resp) resp.value = token;
                        // Fire callbacks registered by the widget
                        try {{
                            Object.entries(___grecaptcha_cfg.clients).forEach(([, client]) => {{
                                if (client && client.R && client.R.callback)
                                    client.R.callback(token);
                            }});
                        }} catch (_) {{}}
                    }}
                """, token)
                print("[CAPTCHA] ✅ reCAPTCHA v2 solved and injected")
                return True

            elif captcha_type == CaptchaType.RECAPTCHA_V3:
                result = await solver.recaptcha(
                    sitekey=sitekey, url=page.url,
                    version='v3', action='submit', score=0.7
                )
                token = result["code"]
                await page.evaluate(f"""
                    (token) => {{
                        const resp = document.getElementById('g-recaptcha-response');
                        if (resp) resp.value = token;
                    }}
                """, token)
                print("[CAPTCHA] ✅ reCAPTCHA v3 solved and injected")
                return True

            elif captcha_type == CaptchaType.HCAPTCHA:
                result = await solver.hcaptcha(sitekey=sitekey, url=page.url)
                token  = result["code"]
                await page.evaluate(f"""
                    (token) => {{
                        const el = document.querySelector('[name="h-captcha-response"]');
                        if (el) el.value = token;
                    }}
                """, token)
                print("[CAPTCHA] ✅ hCaptcha solved and injected")
                return True

            elif captcha_type == CaptchaType.TURNSTILE:
                result = await solver.turnstile(sitekey=sitekey, url=page.url)
                token  = result["code"]
                await page.evaluate(f"""
                    (token) => {{
                        const el = document.querySelector('[name="cf-turnstile-response"]');
                        if (el) el.value = token;
                    }}
                """, token)
                print("[CAPTCHA] ✅ Cloudflare Turnstile solved and injected")
                return True

            else:
                print(f"[CAPTCHA] Auto-solve not supported for type '{captcha_type}'")
                return False

        except Exception as e:
            print(f"[CAPTCHA] 2captcha error: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Manual Telegram fallback
    # ─────────────────────────────────────────────────────────────────────────

    async def request_manual_solve(
        self, page: Page, chat_id: int, request_id: str
    ) -> bool:
        """
        Take a screenshot, send it to the user's Telegram chat, and wait for
        the user to press the ✅ Done button (up to 5 minutes).
        """
        if not self.bot:
            print("[CAPTCHA] No bot instance — cannot send Telegram fallback message")
            return False

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            screenshot = await page.screenshot(type="png")

            event = asyncio.Event()
            self._pending_manual[str(chat_id)] = event

            keyboard = [[
                InlineKeyboardButton(
                    "✅ Done — I solved the CAPTCHA!",
                    callback_data=f"captcha_done_{chat_id}"
                )
            ]]

            await self.bot.send_photo(
                chat_id=chat_id,
                photo=screenshot,
                caption=(
                    "🔒 *CAPTCHA Detected!*\n\n"
                    "A CAPTCHA appeared in the browser window.\n\n"
                    "👉 Please complete it in the browser, then press the button below:\n"
                    "_(Browser stays open — you have up to 5 minutes)_"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )

            print(f"[CAPTCHA] ⏳ Waiting for manual solve (chat_id={chat_id})…")

            await asyncio.wait_for(event.wait(), timeout=300)
            print("[CAPTCHA] ✅ User confirmed CAPTCHA solved")
            return True

        except asyncio.TimeoutError:
            print("[CAPTCHA] ⏱️ Manual CAPTCHA timeout — user did not respond in 5 min")
            self._pending_manual.pop(str(chat_id), None)
            return False
        except Exception as e:
            print(f"[CAPTCHA] Manual solve error: {e}")
            return False

    def signal_captcha_solved(self, chat_id: int) -> bool:
        """
        Called by the Telegram callback handler when the user presses ✅ Done.
        Unblocks the waiting `request_manual_solve` coroutine.
        """
        key = str(chat_id)
        if key in self._pending_manual:
            self._pending_manual[key].set()
            del self._pending_manual[key]
            return True
        return False

    def is_waiting_for_captcha(self, chat_id: int) -> bool:
        return str(chat_id) in self._pending_manual

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Full pipeline
    # ─────────────────────────────────────────────────────────────────────────

    async def handle_captcha(
        self, page: Page, chat_id: int, request_id: str
    ) -> bool:
        """
        Full CAPTCHA handling pipeline:
          detect → auto-solve (if API key present) → manual Telegram fallback.

        Returns True if the CAPTCHA was resolved (or none was found).
        """
        captcha_info = await self.detect_captcha(page)
        captcha_type = captcha_info.get("type", CaptchaType.NONE)

        if captcha_type == CaptchaType.NONE:
            return True  # No CAPTCHA — nothing to do

        print(f"[CAPTCHA] 🚨 Detected CAPTCHA: {captcha_type}")

        # Try 2captcha auto-solve first
        if self.api_key:
            solved = await self.auto_solve(page, captcha_info)
            if solved:
                await asyncio.sleep(1.5)
                return True
            print("[CAPTCHA] Auto-solve failed — falling back to manual")

        # Manual Telegram fallback
        return await self.request_manual_solve(page, chat_id, request_id)
