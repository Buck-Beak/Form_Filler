"""
login_handler.py
~~~~~~~~~~~~~~~~
Detects login pages, attempts automatic credential filling,
and falls back to Telegram prompts when credentials are missing.

Login types detected:
  - username_password  (user-ID + password fields)
  - email_password     (email + password fields)
  - otp                (phone / OTP code only)
  - oauth              (Sign in with Google / Facebook)
  - none               (not a login page)

Credential lookup order:
  1. user_data["extracted_fields"] portal_username / portal_password
  2. user_data PAN / email / mobile as username fallback
  3. users_db portal_credentials dict keyed by domain
  4. Telegram prompt  →  user replies  username:password
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import Page


# ─────────────────────────────────────────────────────────────────────────────
# Login type constants
# ─────────────────────────────────────────────────────────────────────────────

class LoginType:
    USERNAME_PASSWORD = "username_password"
    EMAIL_PASSWORD    = "email_password"
    OTP               = "otp"
    OAUTH             = "oauth"
    NONE              = "none"


# ─────────────────────────────────────────────────────────────────────────────
# LoginHandler
# ─────────────────────────────────────────────────────────────────────────────

class LoginHandler:
    """
    Usage
    -----
    handler = LoginHandler(bot=telegram_bot_instance, users_db=users_list)
    success, msg = await handler.handle_login(page, url, user_data, chat_id)
    """

    def __init__(self, bot=None, users_db: Optional[List[Dict]] = None):
        self.bot      = bot
        self.users_db = users_db or []
        # chat_id (str) -> asyncio.Future[Dict]  — unblocked by signal_credentials_received
        self._pending_creds: Dict[str, "asyncio.Future[Dict]"] = {}
        # "otp_{chat_id}" -> asyncio.Future[str]
        self._pending_otp: Dict[str, "asyncio.Future[str]"]   = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Detection
    # ─────────────────────────────────────────────────────────────────────────

    async def detect_login_type(self, page: Page) -> str:
        """Classify the login page type by inspecting the DOM."""
        try:
            result = await page.evaluate("""
                () => {
                    const text = (document.body && document.body.innerText || '').toLowerCase();
                    const pwdFields   = document.querySelectorAll('input[type="password"]').length;
                    const emailFields = document.querySelectorAll('input[type="email"]').length;

                    const otpPatterns = [
                        'otp', 'one-time', 'verification code',
                        'enter code', 'mobile number', 'aadhaar otp'
                    ];
                    const oauthPatterns = [
                        'sign in with google', 'sign in with facebook',
                        'continue with google', 'login with google'
                    ];

                    const hasOtp   = otpPatterns.some(p => text.includes(p));
                    const hasOauth = oauthPatterns.some(p => text.includes(p));

                    if (hasOtp && pwdFields === 0)              return 'otp';
                    if (hasOauth && pwdFields === 0)            return 'oauth';
                    if (emailFields > 0 && pwdFields > 0)      return 'email_password';
                    if (pwdFields > 0)                          return 'username_password';
                    return 'none';
                }
            """)
            return result or LoginType.NONE
        except Exception as e:
            print(f"[LOGIN] Detection error: {e}")
            return LoginType.NONE

    # ─────────────────────────────────────────────────────────────────────────
    # Credential lookup
    # ─────────────────────────────────────────────────────────────────────────

    def find_credentials(
        self, url: str, user_data: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Search for stored credentials for the given URL domain.

        Returns {"username": ..., "password": ...} or None.
        """
        domain = urlparse(url).netloc.lower()
        fields = user_data.get("extracted_fields", user_data)

        # ── Direct portal credentials ──────────────────────────────────────
        username = (
            fields.get("portal_username")
            or fields.get("username")
        )
        password = (
            fields.get("portal_password")
            or fields.get("password")
        )
        if username and password:
            return {"username": str(username), "password": str(password)}

        # ── Fallback: use PAN / email / mobile as username ─────────────────
        username_fallback = (
            fields.get("panAdhaarUserId")
            or fields.get("pan")
            or fields.get("email")
            or fields.get("mobile")
        )
        if username_fallback and password:
            return {"username": str(username_fallback), "password": str(password)}

        # ── Search users_db for domain-keyed credentials ───────────────────
        for user in self.users_db:
            portal_creds: Dict = user.get("portal_credentials", {})
            for portal_domain, creds in portal_creds.items():
                if portal_domain in domain or domain in portal_domain:
                    return creds

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Auto-fill
    # ─────────────────────────────────────────────────────────────────────────

    async def auto_fill_login(self, page: Page, credentials: Dict[str, str]) -> bool:
        """Find and fill username and password fields."""
        try:
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            
            if not username or not password:
                return False

            # Find username field
            user_selectors = [
                'input[id*="user" i]', 'input[name*="user" i]',
                'input[type="text"]', 'input[type="email"]', 'input[type="tel"]',
                'input[name*="login" i]', 'input[id*="login" i]',
                'input[placeholder*="user" i]', 'input[placeholder*="email" i]',
                'input[placeholder*="login" i]'
            ]
            filled_username = False
            for sel in user_selectors:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.fill(username)
                    filled_username = True
                    print(f"[LOGIN] [OK] Filled username via: {sel}")
                    break
            
            # Find password field
            pass_selectors = [
                'input[type="password"]', 'input[name*="pass" i]', 'input[id*="pass" i]',
                'input[placeholder*="pass" i]'
            ]
            filled_password = False
            for sel in pass_selectors:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.fill(password)
                    filled_password = True
                    print(f"[LOGIN] [OK] Filled password via: {sel}")
                    break
                    
            return filled_username and filled_password
        except Exception as e:
            print(f"[LOGIN] Auto-fill error: {e}")
            return False

    async def handle_remember_me(self, page: Page):
        """Find and click 'Remember Me' or 'Stay Signed In' checkboxes."""
        try:
            selectors = [
                'input[type="checkbox"][name*="remember" i]',
                'input[type="checkbox"][id*="remember" i]',
                'input[type="checkbox"][name*="stay" i]',
                'input[type="checkbox"][id*="stay" i]',
                'input[type="checkbox"][aria-label*="remember" i]',
                'label:has-text("Remember") input',
                'label:has-text("Stay signed in") input',
                'div[role="checkbox"]:has-text("Remember")',
                'span:has-text("Remember")',
            ]
            for sel in selectors:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    # Check if already checked
                    is_checked = await el.is_checked()
                    if not is_checked:
                        try:
                            # Try standard check first
                            await el.check(timeout=2000)
                        except:
                            # Fallback to force click if check fails
                            await el.click(force=True)
                        
                        print(f"[LOGIN] [OK] Clicked 'Remember Me' via: {sel}")
                        return True
        except Exception as e:
            print(f"[LOGIN] Remember Me error: {e}")
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Telegram credential request
    # ─────────────────────────────────────────────────────────────────────────

    async def request_credentials_from_telegram(
        self, chat_id: int, domain: str
    ) -> Optional[Dict[str, str]]:
        """
        Send a Telegram message asking the user for credentials and wait.
        Unblocked when the user replies with  username:password.
        """
        if not self.bot:
            print("[LOGIN] No bot instance — cannot request credentials")
            return None

        key = str(chat_id)
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_creds[key] = fut

        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔐 *Login Required — {domain}*\n\n"
                "Your saved credentials for this portal were not found.\n\n"
                "Please reply with your credentials in this format:\n"
                "`username:password`\n\n"
                "_Example:_ `user@email.com:mypassword123`\n\n"
                "⚠️ Credentials are used once and are NOT stored."
            ),
            parse_mode="Markdown",
        )

        print(f"[LOGIN] Waiting for credentials from Telegram (chat_id={chat_id})…")

        try:
            creds = await asyncio.wait_for(fut, timeout=300)  # 5 min
            return creds
        except asyncio.TimeoutError:
            print("[LOGIN] Credential request timed out")
            self._pending_creds.pop(key, None)
            return None

    def signal_credentials_received(self, chat_id: int, text: str) -> bool:
        """
        Called by the Telegram message handler when the user replies
        with  username:password.  Resolves the pending Future.
        """
        key = str(chat_id)
        if key not in self._pending_creds:
            return False
        if ":" not in text:
            return False
        username, _, password = text.partition(":")
        creds = {"username": username.strip(), "password": password.strip()}
        self._pending_creds[key].set_result(creds)
        del self._pending_creds[key]
        return True

    def is_waiting_for_creds(self, chat_id: int) -> bool:
        return str(chat_id) in self._pending_creds

    # ─────────────────────────────────────────────────────────────────────────
    # OTP handling
    # ─────────────────────────────────────────────────────────────────────────

    async def request_otp(self, chat_id: int) -> Optional[str]:
        """Ask the user for an OTP via Telegram and wait for their reply."""
        if not self.bot:
            return None

        key = f"otp_{chat_id}"
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_otp[key] = fut

        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                "📱 *OTP Required*\n\n"
                "An OTP / verification code has been sent to your registered "
                "phone number or email.\n\n"
                "Please reply with the OTP code:"
            ),
            parse_mode="Markdown",
        )

        print(f"[LOGIN] Waiting for OTP from Telegram (chat_id={chat_id})…")

        try:
            otp = await asyncio.wait_for(fut, timeout=300)
            return otp
        except asyncio.TimeoutError:
            print("[LOGIN] OTP request timed out")
            self._pending_otp.pop(key, None)
            return None

    def signal_otp_received(self, chat_id: int, otp: str) -> bool:
        key = f"otp_{chat_id}"
        if key not in self._pending_otp:
            return False
        self._pending_otp[key].set_result(otp.strip())
        del self._pending_otp[key]
        return True

    def is_waiting_for_otp(self, chat_id: int) -> bool:
        return f"otp_{chat_id}" in self._pending_otp

    # ─────────────────────────────────────────────────────────────────────────
    # Submit helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _submit_login_form(self, page: Page) -> None:
        """Click the login/submit button or press Enter."""
        try:
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'input[type="button"][value*="Login" i]',
                'input[type="button"][value*="Sign In" i]',
                'input[type="button"][value*="Submit" i]',
                'button:has-text("Login")',
                'button:has-text("Sign In")',
                'button:has-text("Log In")',
                'button:has-text("Submit")',
                'button:has-text("Continue")',
                'a.btn:has-text("Login")',
                '[role="button"]:has-text("Login")'
            ]
            for sel in submit_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    print(f"[LOGIN] [OK] Login form submitted via button: {sel}")
                    return
        except Exception as e:
            print(f"[LOGIN] Submit button error: {e}")
        # Fallback: Enter key
        await page.keyboard.press("Enter")
        print("[LOGIN] [OK] Login form submitted via Enter key")

    # ─────────────────────────────────────────────────────────────────────────
    # Full pipeline
    # ─────────────────────────────────────────────────────────────────────────

    async def handle_login(
        self,
        page: Page,
        url: str,
        user_data: Dict[str, Any],
        chat_id: int,
    ) -> Tuple[bool, str]:
        """
        Full login pipeline:
          detect type → handle preferences → find/request credentials → fill → handle OTP → submit.
        """
        login_type = await self.detect_login_type(page)
        print(f"[LOGIN] Login type: {login_type}  |  URL: {url[:60]}")

        if login_type == LoginType.NONE:
            return False, "Not a login page"

        # ── Check Preferences ──────────────────────────────────────────────
        fields = user_data.get("extracted_fields", user_data)
        auto_login_pref = fields.get("auto_login", True)
        remember_me_pref = fields.get("remember_me", False)

        if not auto_login_pref:
            if self.bot:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text="⏳ *Auto-Login Disabled*\n\nPlease log in manually in the browser. I'll wait here.",
                    parse_mode="Markdown"
                )
            return False, "Auto-login disabled by user"

        if login_type == LoginType.OAUTH:
            if self.bot:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🔐 *OAuth Login Required*\n\n"
                        "This portal uses Google / Facebook sign-in.\n"
                        "Please log in manually in the browser window.\n"
                        "_(The bot will continue once you are logged in.)_"
                    ),
                    parse_mode="Markdown",
                )
            return False, "OAuth login — manual intervention required"

        domain = urlparse(url).netloc

        # ── Find credentials ───────────────────────────────────────────────
        credentials = self.find_credentials(url, user_data)
        if not credentials:
            print(f"[LOGIN] No saved credentials for {domain} — asking user…")
            credentials = await self.request_credentials_from_telegram(chat_id, domain)

        if not credentials:
            return False, f"No credentials available for {domain}"

        # ── Fill the form ──────────────────────────────────────────────────
        filled = await self.auto_fill_login(page, credentials)
        if not filled:
            return False, "Could not fill the login form"

        # ── Handle Remember Me ─────────────────────────────────────────────
        if remember_me_pref:
            await self.handle_remember_me(page)

        # ── Initial Submit ─────────────────────────────────────────────────
        await asyncio.sleep(0.5)
        await self._submit_login_form(page)
        
        # ── Monitor for 2FA / Post-Submit OTP (Dual Entry) ──────────────────
        # We wait up to 10 seconds to see if an OTP prompt or login error appears
        print("[LOGIN] Monitoring for post-submission challenges...")
        start_url = page.url
        
        for _ in range(5):
            await asyncio.sleep(2)
            
            # 1. Did we successfully log in (URL changed significantly)?
            if page.url != start_url and "/login" not in page.url.lower():
                print("[LOGIN] URL changed. Likely successful login.")
                return True, "Login successful"

            # 2. Did a 2FA/OTP field appear?
            new_type = await self.detect_login_type(page)
            if new_type == LoginType.OTP:
                print("[LOGIN] 2FA OTP detected. Starting dual-entry monitor.")
                if self.bot:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "📱 *2FA OTP Required*\n\n"
                            "The website is asking for a second verification code.\n\n"
                            "👉 You can *reply with the code here* OR *enter it yourself* in the browser."
                        ),
                        parse_mode="Markdown"
                    )
                
                # Setup dual monitor
                key = f"otp_{chat_id}"
                loop = asyncio.get_event_loop()
                fut: asyncio.Future = loop.create_future()
                self._pending_otp[key] = fut
                
                try:
                    # Wait for either Telegram reply OR page change (manual entry)
                    wait_count = 0
                    while wait_count < 150: # 5 minutes total
                        # Check Telegram
                        if fut.done():
                            otp_code = fut.result()
                            print(f"[LOGIN] Entering Telegram-provided OTP: {otp_code}")
                            otp_selectors = ['input[placeholder*="OTP" i]', 'input[name*="otp" i]', 'input[id*="otp" i]', 'input[placeholder*="code" i]']
                            for sel in otp_selectors:
                                el = page.locator(sel).first
                                if await el.count() > 0:
                                    await el.type(otp_code, delay=50)
                                    await page.keyboard.press("Enter")
                                    break
                            return True, "OTP entered via Telegram"
                        
                        # Check Manual Entry (URL changed or field gone)
                        if page.url != start_url and "/login" not in page.url.lower():
                            print("[LOGIN] Detected manual 2FA entry in browser.")
                            self._pending_otp.pop(key, None)
                            return True, "OTP entered manually in browser"
                        
                        # Check if OTP field is still there
                        is_otp_still_there = await page.evaluate("""
                            () => document.querySelectorAll('input[type="text"], input[type="tel"]').length > 0
                        """)
                        if not is_otp_still_there and page.url != start_url:
                            print("[LOGIN] OTP field gone. Likely manual entry.")
                            self._pending_otp.pop(key, None)
                            return True, "OTP cleared manually"

                        await asyncio.sleep(2)
                        wait_count += 1
                finally:
                    self._pending_otp.pop(key, None)

        return True, f"Login attempted for {domain}"
