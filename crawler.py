"""
crawler.py
~~~~~~~~~~
WebCrawler — the top-level orchestrator that wraps NavigationAgent and adds:

  • Multi-depth crawling with breadth-first backtracking (same-domain only)
  • Login auto-fill via LoginHandler (Telegram fallback when creds missing)
  • CAPTCHA handling via CaptchaHandler (2captcha API + Telegram manual fallback)
  • Visited-URL deduplication to avoid loops
  • Scored link extraction weighted by intent keywords

Typical call from main.py:
    crawler = WebCrawler(page, gemini_model, bot=bot, chat_id=chat_id,
                         user_data=user_data, users_db=users_db, request_id=req_id)
    found, final_url, reason = await crawler.crawl(url, form_key, max_depth=8)
"""

import asyncio
import random
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import google.generativeai as genai
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from captcha_handler import CaptchaHandler
from login_handler import LoginHandler
from navigation_agent import NavigationAgent, NavigationBlockedError
from session_storage import SessionStorage
from visual_feedback import VisualFeedback


class WebCrawler:
    """
    Multi-depth crawler that wraps NavigationAgent.

    Architecture
    ------------
    Stage 1 — NavigationAgent (AI-guided, up to max_depth attempts)
        Handles SPAs, Angular/React portals, element scoring, Gemini picks.
        Login / CAPTCHA events are intercepted here via injected handlers.

    Stage 2 — Login retry (if Stage 1 stopped at a login wall)
        LoginHandler fills credentials → re-runs NavigationAgent.

    Stage 3 — BFS link crawl (last resort)
        Iterates same-domain links scored by intent keywords, visits them,
        checks for form presence at each node.
    """

    def __init__(
        self,
        page: Page,
        gemini_model: genai.GenerativeModel,
        bot=None,
        chat_id: Optional[int] = None,
        user_data: Optional[Dict[str, Any]] = None,
        users_db: Optional[List[Dict]] = None,
        request_id: Optional[str] = None,
    ):
        self.page       = page
        self.model      = gemini_model
        self.bot        = bot
        self.chat_id    = chat_id
        self.user_data  = user_data or {}
        self.request_id = request_id or ""

        # ── Sub-handlers ──────────────────────────────────────────────────
        self.captcha_handler = CaptchaHandler(bot=bot)
        self.login_handler   = LoginHandler(bot=bot, users_db=users_db or [])
        self.session_storage = SessionStorage()
        self.visual          = VisualFeedback(page)

        # ── NavigationAgent gets our handlers injected ────────────────────
        self.nav_agent = NavigationAgent(
            playwright_page  = page,
            gemini_model     = gemini_model,
            bot              = bot,
            login_handler    = self.login_handler,
            captcha_handler  = self.captcha_handler,
            chat_id          = chat_id,
            user_data        = user_data,
        )

        self.start_domain: str = ""

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def crawl(
        self,
        start_url: str,
        intent: str,
        max_depth: int = 8,
    ) -> Tuple[bool, str, str]:
        """
        Navigate from start_url towards a form page that matches intent.

        Returns
        -------
        (found_form: bool, final_url: str, reason: str)
        """
        self.start_domain = urlparse(start_url).netloc
        await self.visual.inject_visual_styles()

        print(f"\n[Crawler] 🕷️  Starting crawl")
        print(f"[Crawler]    URL    : {start_url}")
        print(f"[Crawler]    Intent : {intent}")
        print(f"[Crawler]    Depth  : {max_depth}")

        # ── Unified Reactive Navigation ──────────────────────────────────
        try:
            found, final_url, reason = await self.nav_agent.maps_to_form(
                start_url, intent, max_attempts=max_depth
            )
            return found, final_url, reason
            
        except NavigationBlockedError as block_err:
            return False, self.page.url, f"Navigation blocked: {block_err}"
        except Exception as e:
            print(f"[Crawler] Error during crawl: {e}")
            return False, self.page.url, f"Crawl error: {str(e)}"

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2 helper — login handling
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_login_then_continue(
        self, start_url: str, intent: str
    ) -> bool:
        """
        Attempt to log in automatically, then check for CAPTCHA that may
        appear post-login.  Returns True if login was handled successfully.
        """
        login_ok, login_msg = await self.login_handler.handle_login(
            self.page, self.page.url, self.user_data, self.chat_id or 0
        )

        if login_ok:
            print(f"[Crawler] ✅ Login OK: {login_msg}")
            await asyncio.sleep(3)
            # Check for post-login CAPTCHA
            captcha_info = await self.captcha_handler.detect_captcha(self.page)
            if captcha_info.get("type") != "none":
                await self.captcha_handler.handle_captcha(
                    self.page, self.chat_id or 0, self.request_id
                )
            return True

        print(f"[Crawler] ❌ Login failed: {login_msg}")
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3 — BFS crawl
    # ─────────────────────────────────────────────────────────────────────────

    async def _bfs_crawl(
        self, start_url: str, intent: str, max_depth: int
    ) -> Tuple[bool, str, str]:
        """
        Breadth-first crawl over same-domain links.
        At each visited page:
          • Check for CAPTCHA → handle
          • Check for login page → handle
          • Check for form → return success
          • Score outgoing links → enqueue top candidates
        """
        queue: List[Tuple[str, int]] = [(start_url, 0)]
        visited: Set[str] = set()
        pages_checked = 0

        while queue:
            url, depth = queue.pop(0)

            if depth > max_depth:
                continue
            if url in visited:
                continue
            visited.add(url)
            pages_checked += 1

            # ── Navigate (skip if already on this URL) ────────────────────
            if self._normalize_url(self.page.url) != self._normalize_url(url):
                try:
                    await self.page.goto(
                        url, wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(random.uniform(1.5, 2.5))
                except PlaywrightTimeoutError:
                    print(f"[Crawler] ⏱️ Timeout navigating to {url}")
                    continue
                except Exception as e:
                    print(f"[Crawler] ⚠️ Navigation error for {url}: {e}")
                    continue

            await self.visual.show_thinking(
                f"BFS depth {depth} | checked {pages_checked} pages"
            )

            # ── CAPTCHA check ─────────────────────────────────────────────
            captcha_info = await self.captcha_handler.detect_captcha(self.page)
            if captcha_info.get("type") != "none":
                print(f"[Crawler] 🔒 BFS: CAPTCHA at {url}")
                resolved = await self.captcha_handler.handle_captcha(
                    self.page, self.chat_id or 0, self.request_id
                )
                if not resolved:
                    continue  # Skip this URL and try next

            # ── Login check ───────────────────────────────────────────────
            if await self.nav_agent._is_login_page():
                print(f"[Crawler] 🔐 BFS: Login page at {url}")
                login_ok = await self._handle_login_then_continue(url, intent)
                if not login_ok:
                    continue

            # ── Form check (success!) ─────────────────────────────────────
            if await self.nav_agent._has_form():
                print(
                    f"[Crawler] ✅ BFS found form at depth {depth}: {self.page.url}"
                )
                return (
                    True,
                    self.page.url,
                    f"BFS crawl found form at depth {depth} "
                    f"({pages_checked} pages checked)",
                )

            # ── Enqueue top-scored links for next level ───────────────────
            if depth < max_depth:
                links = await self._extract_scored_links(intent)
                print(
                    f"[Crawler] 🔗 BFS depth {depth}: "
                    f"{len(links)} scored links queued from {url}"
                )
                for link_url, _score in links[:8]:
                    if link_url not in visited:
                        queue.append((link_url, depth + 1))

        return (
            False,
            self.page.url,
            f"BFS crawl exhausted after checking {pages_checked} pages",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Link extraction helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _extract_scored_links(
        self, intent: str
    ) -> List[Tuple[str, float]]:
        """
        Extract all same-domain <a href> links from the current page,
        score them by intent-keyword overlap + form-indicator keywords,
        and return a sorted list of (url, score).
        """
        form_keywords = [
            "apply", "application", "register", "registration", "form",
            "signup", "sign up", "join", "enroll", "admission", "fill",
            "start", "begin", "proceed", "next", "continue", "submit",
            "new", "fresh", "file", "upload", "verify", "create", "open",
            "online", "portal", "dashboard", "service", "login", "exam",
        ]
        skip_terms = [
            "logout", "privacy", "terms", "cookie", "faq",
            "print", "download", "share", "accessibility",
        ]
        intent_words = set(intent.lower().split())

        try:
            raw: List[Dict] = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({ href: a.href, text: (a.textContent || '').trim() }))
                    .filter(l => l.href.startsWith('http') && l.text.length > 1)
                    .slice(0, 120)
            """)
        except Exception as e:
            print(f"[Crawler] Link extraction error: {e}")
            return []

        scored: List[Tuple[str, float]] = []
        for item in raw:
            href = item.get("href", "")
            text = item.get("text", "").lower()

            # Same-domain only
            if urlparse(href).netloc != self.start_domain:
                continue

            # Skip noise
            if any(s in text for s in skip_terms):
                continue

            # Score
            kw_score     = sum(1 for kw in form_keywords if kw in text) * 0.1
            intent_score = len(intent_words & set(text.split())) * 0.3
            url_score    = sum(1 for kw in form_keywords if kw in href.lower()) * 0.05
            total_score  = kw_score + intent_score + url_score

            scored.append((href, total_score))

        # Deduplicate by URL, keep highest score
        seen: Dict[str, float] = {}
        for url, score in scored:
            if url not in seen or score > seen[url]:
                seen[url] = score

        result = sorted(seen.items(), key=lambda x: x[1], reverse=True)
        return result

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip trailing slash and fragment for comparison."""
        return url.rstrip("/").split("#")[0].split("?")[0]
