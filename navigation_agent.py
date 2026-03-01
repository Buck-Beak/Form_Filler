import asyncio
import random
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import google.generativeai as genai
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from visual_feedback import VisualFeedback
from session_storage import SessionStorage


class NavigationBlockedError(Exception):
    """Raised when navigation is blocked by access control or CAPTCHA."""


class LoginDetectedError(Exception):
    """Raised when a login page is detected"""
    pass


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


class NavigationAgent:
    """Autonomous navigator to reach the target form page with visual feedback and learning."""

    def __init__(
        self,
        playwright_page: Page,
        gemini_model: genai.GenerativeModel,
        bot=None,
        login_handler=None,
        captcha_handler=None,
        chat_id: Optional[int] = None,
        user_data: Optional[Dict] = None,
    ):
        self.page = playwright_page
        self.model = gemini_model
        self.bot = bot
        self.visual = VisualFeedback(playwright_page)
        self.session_storage = SessionStorage()
        self.current_session_steps = []
        self.start_time = None
        # Injected handlers (supplied by WebCrawler; fall back to None = old behaviour)
        self.login_handler   = login_handler
        self.captcha_handler = captcha_handler
        self.chat_id         = chat_id
        self.user_data       = user_data or {}
        
        #  State for Unified Flow 
        self.nav_stack = []        # List of (url, elements_tried) for backtracking
        self.visited_urls = set()  # URLs visited in current crawl to avoid loops
        self.is_paused = False     # Flag for human interaction pause
        self.last_known_url = None # Tracking for "Resume" detection

    async def _think(self, user_intent: str, elements: List[Dict[str, Any]]) -> str:
        """Explicit reasoning step using Gemini to analyze the page and plan next move."""
        await self.visual.show_thinking("Analyzing page state...")
        
        # Prepare context
        element_summary = "\n".join([
            f"- [{e['type']}] {e['text']} (Priority: {e['priority']:.1f})"
            for e in elements[:10]
        ])
        
        prompt = (
            f"You are the Navigation Agent. Current Goal: {user_intent}\n"
            f"Current Page: {await self.page.title()}\n"
            f"URL: {self.page.url}\n\n"
            f"Top Elements Detected:\n{element_summary}\n\n"
            "TASK: Describe your current 'thought' about this page in one concise sentence (max 15 words).\n"
            "Focus on what you see and what you are looking for next.\n"
            "THOUGHT:"
        )
        
        try:
            resp = self.model.generate_content(prompt)
            thought = (resp.text or "Analyzing available links to find the application form.").strip()
            thought = thought.replace('"', '').replace("'", "") # Clean up
            await self.visual.add_thought(thought)
            return thought
        except Exception as e:
            fallback = "Analyzing layout to determine the best path to the form."
            await self.visual.add_thought(fallback)
            return fallback

    async def maps_to_form(self, start_url: str, user_intent: str, max_attempts: int = 20) -> Tuple[bool, str, str]:
        """
        Unified Reactive Flow: Look -> Detect Blockers -> Think -> Act -> Backtrack.
        """
        self.start_time = datetime.now()
        self.nav_stack = []
        self.visited_urls = set()
        
        # Memory check
        previous_sessions = self.session_storage.get_successful_paths(start_url, user_intent)
        if previous_sessions:
            await self.visual.add_thought("Recalling successful paths from previous sessions...")
            if await self._replay_successful_path(previous_sessions[0], user_intent):
                return True, self.page.url, "Success from memory"

        try:
            await self.page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
        except Exception as e:
            return False, start_url, f"Initial load failed: {e}"

        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            current_url = self.page.url
            self.last_known_url = current_url
            
            # 1. LOOK & DETECT (React to page state)
            state = await self._detect_page_state()
            
            if state == "form":
                await self.visual.add_thought("Form detected!")
                return True, current_url, "Found target form"
                
            if state == "captcha":
                await self._handle_captcha_loop()
                continue # Re-evaluate state after solve
                
            if state == "login":
                await self.visual.add_thought("Login wall detected.")
                login_success = await self._handle_login_reactive()
                if not login_success:
                    await self.visual.add_thought("Login failed. Waiting for human...")
                    await self._wait_for_human("Login failed. Please login manually or provide credentials.")
                continue

            # 2. ANALYZE & THINK
            elements = await self._extract_smart_elements(user_intent)
            if not elements:
                if await self._backtrack():
                    continue
                return False, current_url, "Exhausted all paths"

            # Filter out elements already tried from this URL in the nav_stack
            tried_indices = self._get_tried_indices(current_url)
            available = [e for i, e in enumerate(elements) if i not in tried_indices]
            
            if not available:
                if await self._backtrack():
                    continue
                return False, current_url, "Exhausted links at this node"

            await self._think(user_intent, available)
            
            # 3. ACT
            choice_idx_in_available = await self._choose_best_element(user_intent, available)
            if choice_idx_in_available is None:
                if await self._backtrack(): continue
                return False, current_url, "No relevant links"
            
            selected = available[choice_idx_in_available]
            # Map choice back to original index in 'elements'
            original_idx = elements.index(selected)
            
            # Record choice in stack before acting
            self._push_stack(current_url, original_idx)
            
            await self.visual.add_thought(f"Navigating: '{selected['text']}'")
            success = await self._click_element_safe(selected)
            
            if success:
                await asyncio.sleep(2)
                self.visited_urls.add(current_url)
            else:
                await self.visual.add_thought("Click failed, trying next option.")
                # Current index already recorded in stack, loop will pick next
                
        return False, self.page.url, "Max attempts reached"
    
    # 
    # Session Management Methods
    # 
    
    def _record_step(self, url: str, action: str, details: str):
        """Record a navigation step"""
        step = {
            "url": url,
            "action": action,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "is_login_page": False  # Will be updated if login detected
        }
        self.current_session_steps.append(step)
        print(f"[Session] Recorded: {action} - {details}")
    
    async def _save_successful_session(self, start_url: str, user_intent: str, final_url: str):
        """Save successful navigation session"""
        session_data = {
            "start_url": start_url,
            "user_intent": user_intent,
            "final_url": final_url,
            "success": True,
            "form_found": True,
            "form_filled": False,  # Will be updated later
            "fields_filled_count": 0,  # Will be updated later
            "steps_taken": self.current_session_steps,
            "duration_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            "error": None
        }
        self.session_storage.save_session(session_data)
        print("[Session] Saved successful session")
    
    async def _save_failed_session(self, start_url: str, user_intent: str, error: str):
        """Save failed navigation session"""
        session_data = {
            "start_url": start_url,
            "user_intent": user_intent,
            "final_url": self.page.url,
            "success": False,
            "form_found": False,
            "form_filled": False,
            "fields_filled_count": 0,
            "steps_taken": self.current_session_steps,
            "duration_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            "error": error
        }
        self.session_storage.save_session(session_data)
        print(f"[Session] Saved failed session: {error}")
    
    async def _replay_successful_path(self, previous_session: Dict, user_intent: str) -> bool:
        """Try to replay a previously successful navigation path"""
        print(f"[NAV] Attempting to replay successful path from previous session")
        
        steps = previous_session.get('steps_taken', [])
        for i, step in enumerate(steps):
            if step.get('action') == 'click':
                print(f"[NAV]  Replaying step {i+1}/{len(steps)}: {step.get('details', '')}")
                await self.visual.show_action_overlay("Replaying", f"Step {i+1}: {step.get('details', '')[:40]}")
                
                # Try to find and click the same element
                element_text = step.get('details', '')
                try:
                    # Try to find element by text
                    element = self.page.get_by_text(element_text, exact=False).first
                    if await element.count() > 0:
                        await element.click()
                        await asyncio.sleep(2)
                        
                        # Check if we reached the form
                        if await self._has_form():
                            print("[NAV] Form found during replay!")
                            return True
                except Exception as e:
                    print(f"[NAV]  Replay step failed: {e}")
                    # Continue to next step
                    continue
        
        # Check final result
        if await self._has_form():
            print("[NAV]  Form found after full replay!")
            return True
        
        print("[NAV]  Replay did not reach form, falling back to normal navigation")
        return False
    
    # 
    # Detection Methods
    # 
    
    # 
    # Unified Reactive Flow Helpers
    # 

    async def _detect_page_state(self) -> str:
        """Classify current page as Form, Login, CAPTCHA, or Normal."""
        if await self._has_form():
            return "form"
        
        if self.captcha_handler:
            cap = await self.captcha_handler.detect_captcha(self.page)
            if cap.get("type") != "none":
                return "captcha"
        
        if await self._is_login_page():
            return "login"
            
        block_msg = await self._is_blocked()
        if block_msg:
            print(f"[NAV] Blocked: {block_msg}")
            
        return "normal"

    async def _handle_captcha_loop(self):
        """Watcher loop: Notify user and poll every 5s until CAPTCHA is gone."""
        await self.visual.add_thought("CAPTCHA detected. Please solve it in the browser.")
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text="CAPTCHA detected!\nPlease solve it in the browser window. I will resume automatically once it's cleared."
                )
            except: pass
        
        while True:
            cap = await self.captcha_handler.detect_captcha(self.page)
            if cap.get("type") == "none":
                await self.visual.add_thought("CAPTCHA solved! Resuming...")
                break
            await asyncio.sleep(5)

    async def _handle_login_reactive(self) -> bool:
        """Reactive login: attempt auto-fill, if error detected, return False for handoff."""
        if not self.login_handler: return False
        
        success, msg = await self.login_handler.handle_login(
            self.page, self.page.url, self.user_data, self.chat_id or 0
        )
        
        if success:
            await asyncio.sleep(3)
            # Check for error messages post-submission
            error_detected = await self.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    const errors = ['invalid', 'incorrect', 'failed', 'wrong', 'try again', 'error'];
                    return errors.some(e => text.includes(e));
                }
            """)
            if error_detected:
                print("[NAV] Login error detected after submit.")
                return False
            return True
        return False

    async def _wait_for_human(self, message: str):
        """Pause bot and wait for user to signal 'resume' or page to change significantly."""
        await self.visual.add_thought(f"Bot Paused: {message}")
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=f" **Bot Paused**\n{message}\n\nType 'continue' or 'next' to resume after resolving."
                )
            except: pass
        
        self.is_paused = True
        start_url = self.page.url
        while self.is_paused:
            # Check if user manually navigated or page changed
            if self.page.url != start_url:
                await self.visual.add_thought("Detected page change. Resuming...")
                self.is_paused = False
                break
            await asyncio.sleep(2)

    def _get_tried_indices(self, url: str) -> List[int]:
        return [item[1] for item in self.nav_stack if item[0] == url]

    def _push_stack(self, url: str, element_idx: int):
        self.nav_stack.append((url, element_idx))

    async def _backtrack(self) -> bool:
        """Try to go back and find another path."""
        if not self.nav_stack:
            return False
            
        await self.visual.add_thought("Reached a dead end. Backtracking...")
        try:
            # Pop the current URL
            if self.nav_stack:
                self.nav_stack.pop()
                
            await self.page.go_back()
            await asyncio.sleep(2)
            return True
        except:
            return False

    async def _is_login_page(self) -> bool:
        """Simple classification of login page."""
        try:
            return await self.page.evaluate("""
                () => {
                    const pwdFields = document.querySelectorAll('input[type="password"]').length;
                    const text = document.body.innerText.toLowerCase();
                    const loginKeywords = ['login', 'sign in', 'log in', 'account', 'credential'];
                    const hasLoginKeyword = loginKeywords.some(kw => text.includes(kw));
                    return pwdFields > 0 || (hasLoginKeyword && document.querySelectorAll('input').length > 0);
                }
            """)
        except:
            return False

    async def _is_blocked(self) -> Optional[str]:
        content = (await self.page.content()).lower()[:6000]
        title = (await self.page.title()).lower()
        blocked_markers = ["access denied", "permission denied", "forbidden", "403", "captcha"]
        for marker in blocked_markers:
            if marker in content or marker in title:
                return f"Blocked by page: {marker}"
        return None

    async def _has_form(self) -> bool:
        """Strictly check if page has an actual form with input fields."""
        try:
            result = await self.page.evaluate(
                """
                () => {
                    // STRICT: Only count actual fillable form fields
                    const inputs = Array.from(document.querySelectorAll(
                        'input[type="text"], input[type="email"], input[type="password"], ' +
                        'input[type="number"], input[type="date"], input[type="tel"], ' +
                        'textarea, select'
                    ))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const style = window.getComputedStyle(el);
                        const displayed = style.display !== 'none' && style.visibility !== 'hidden';
                        return visible && displayed;
                    });
                    
                    // Count actual form elements
                    const forms = document.querySelectorAll('form');
                    
                    // Check for form-like containers (common in SPA/React apps)
                    const formContainers = document.querySelectorAll(
                        '[class*="form"], [class*="Form"], [id*="form"], [id*="Form"], ' +
                        '[data-testid*="form"], [role="form"]'
                    );
                    
                    // REQUIRE at least 1 visible input field OR 1 form element
                    // (relaxed from 2+ to handle single-field pages and SPA delays)
                    const hasForm = inputs.length >= 1 || forms.length >= 1 || formContainers.length > 0;
                    
                    console.log('Form detection:', {
                        inputs: inputs.length, 
                        forms: forms.length,
                        formContainers: formContainers.length,
                        detected: hasForm
                    });
                    
                    return {
                        found: hasForm,
                        inputCount: inputs.length,
                        formCount: forms.length,
                        formContainers: formContainers.length
                    };
                }
                """
            )
            
            has_form = result.get("found", False)
            input_count = result.get("inputCount", 0)
            form_containers = result.get("formContainers", 0)
            
            if has_form:
                print(f"[FormDetection] Found form with {input_count} inputs, {form_containers} form containers")
            else:
                print(f"[FormDetection] No form detected (inputs: {input_count}, containers: {form_containers})")
            
            return has_form
            
        except Exception as e:
            print(f"[NAV] Form detection error: {e}")
            return False

    # 
    # SPA and Smart Navigation Methods
    # 
    
    async def _handle_spa_navigation(self, user_intent: str) -> bool:
        """Special handling for Single Page Applications (React, Vue, Angular)"""
        print("[NAV] Using SPA-specific navigation...")
        
        # Wait longer for SPA to fully load
        await asyncio.sleep(3)
        await self.visual.show_thinking("Waiting for SPA to load...")
        
        # Try clicking visible, form-related buttons
        button_selectors = [
            "button:visible",
            "[role='button']:visible",
            "a.btn:visible",
            "[data-testid]:visible",
            ".mat-button:visible",  # Angular Material
            ".v-btn:visible"  # Vuetify
        ]
        
        form_keywords = ["verify", "return", "continue", "proceed", "new", "fresh", "file", 
                        "start", "begin", "apply", "register", "form", "fill"]
        
        for selector in button_selectors:
            try:
                buttons = await self.page.locator(selector).all()
                for btn in buttons[:10]:  # Check first 10 buttons
                    try:
                        btn_text = await btn.inner_text()
                        if not btn_text or len(btn_text) < 2:
                            continue
                        
                        # Check if button text matches intent
                        if any(kw in btn_text.lower() for kw in form_keywords):
                            print(f"[NAV]  Found SPA button: {btn_text[:40]}")
                            await self.visual.show_clicking(btn_text)
                            
                            await btn.click()
                            await asyncio.sleep(3)  # SPAs need time to render
                            
                            if await self._has_form():
                                print(f"[NAV] Form found after SPA button click!")
                                self._record_step(self.page.url, "spa_click", btn_text)
                                return True
                    except Exception as e:
                        print(f"[NAV] Button click attempt failed: {e}")
                        continue
            except Exception:
                continue
        
        return False
    
    async def _try_spa_blind_clicks(self, user_intent: str) -> bool:
        """
        Fallback: Try intelligently clicking visible buttons when no links found
        Useful for SPAs that don't have traditional href links
        """
        print("[NAV] Trying intelligent button clicks for SPA...")
        
        # Get all visible, clickable elements
        clickable_elements = await self.page.evaluate("""
            () => {
                const elements = [];
                
                // Get all buttons and button-like elements
                const selectors = [
                    'button', '[role="button"]', '[type="button"]',
                    '[type="submit"]', 'a', '.btn', '.button'
                ];
                
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const style = window.getComputedStyle(el);
                        const displayed = style.display !== 'none' && style.visibility !== 'hidden';
                        
                        if (visible && displayed) {
                            elements.push({
                                text: el.textContent.trim(),
                                tag: el.tagName.toLowerCase(),
                                className: el.className,
                                id: el.id,
                                index: elements.length
                            });
                        }
                    });
                });
                
                return elements.slice(0, 15);  // Return first 15 visible elements
            }
        """)
        
        if not clickable_elements:
            print("[NAV] No clickable elements found")
            return False
        
        print(f"[NAV] Found {len(clickable_elements)} clickable elements")
        
        # Score and sort elements by relevance
        form_keywords = ["form", "apply", "register", "start", "begin", "continue", "proceed", 
                        "next", "new", "fill", "submit", "enter"]
        
        for element in clickable_elements:
            text = element.get('text', '').lower()
            score = sum(1 for kw in form_keywords if kw in text)
            element['score'] = score
        
        # Sort by score (highest first)
        clickable_elements.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Try clicking top 5 most relevant buttons
        for element in clickable_elements[:5]:
            if element.get('score', 0) == 0:
                continue  # Skip if no relevant keywords
            
            print(f"[NAV] Trying: {element.get('text', '')[:40]} (score: {element.get('score')})")
            await self.visual.show_clicking(element.get('text', '')[:40])
            
            try:
                # Try to find and click the element
                text = element.get('text', '')
                if text:
                    locator = self.page.get_by_text(text, exact=False).first
                    if await locator.count() > 0:
                        await locator.click()
                        await asyncio.sleep(2)
                        
                        if await self._has_form():
                            print(f"[NAV] Form found after blind click!")
                            self._record_step(self.page.url, "blind_click", text)
                            return True
            except Exception as e:
                print(f"[NAV] Click failed: {e}")
                continue
        
        return False
    
    async def _extract_smart_elements(self, user_intent: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Enhanced element extraction with better detection of clickable elements
        Handles traditional links, buttons, and SPA elements
        """
        print("[NAV] Extracting navigable elements...")
        
        candidates: List[Dict[str, Any]] = []
        
        # Enhanced selectors covering more cases
        element_groups = [
            {
                "selector": "a[href]",
                "type": "link",
                "priority_boost": 1.0
            },
            {
                "selector": "button:not([disabled])",
                "type": "button",
                "priority_boost": 1.2
            },
            {
                "selector": "[role='button']",
                "type": "role-button",
                "priority_boost": 1.1
            },
            {
                "selector": "input[type='submit'], input[type='button']",
                "type": "input-button",
                "priority_boost": 1.0
            },
            {
                "selector": "[data-testid], [data-test]",
                "type": "test-element",
                "priority_boost": 0.9
            },
            {
                "selector": ".btn, .button, .mat-button, .v-btn",
                "type": "css-button",
                "priority_boost": 1.0
            }
        ]
        
        # Form-related keywords (high priority)
        form_indicators = [
            "apply", "application", "register", "registration", "form", "exam",
            "signup", "sign up", "join", "participate", "enroll", "admission",
            "fill", "start", "begin", "proceed", "next", "continue", "submit",
            "new", "fresh", "file", "upload", "verify", "create", "open"
        ]
        
        # Skip these (low priority)
        skip_terms = [
            "privacy", "terms", "cookie", "faq", "help", "support",
            "footer", "contact", "about", "back", "logout", "exit",
            "close", "cancel", "share", "print", "download", "search"
        ]
        
        for group in element_groups:
            try:
                locator = self.page.locator(group["selector"] + ":visible")
                count = min(await locator.count(), 100)
                
                for i in range(count):
                    try:
                        handle = locator.nth(i)
                        
                        # Get element properties
                        text = _normalize_text(await handle.inner_text())
                        href = await handle.get_attribute("href") or ""
                        
                        if not text or len(text) < 2:
                            continue
                        
                        lower_text = text.lower()
                        
                        # Skip irrelevant elements
                        if any(term in lower_text for term in skip_terms):
                            continue
                        
                        # Calculate priority based on keywords
                        is_form_related = any(term in lower_text for term in form_indicators)
                        base_priority = 2.0 if is_form_related else 1.0
                        priority = base_priority * group["priority_boost"]
                        
                        # Check if this element already exists (by text)
                        exists = any(c["text"].lower() == text.lower() for c in candidates)
                        if exists:
                            continue
                        
                        candidates.append({
                            "index": i,
                            "text": text[:100],
                            "href": href,
                            "type": group["type"],
                            "priority": priority,
                            "is_form_link": is_form_related,
                            "selector": group["selector"]
                        })
                        
                        if len(candidates) >= limit * 2:  # Get more candidates initially
                            break
                    except Exception as e:
                        # Element might be stale or hidden
                        continue
            except Exception as e:
                print(f"[NAV] Error with selector {group['selector']}: {e}")
                continue
        
        # Sort by priority (highest first)
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        
        # Return top candidates
        top_candidates = candidates[:limit]
        print(f"[NAV]  Found {len(top_candidates)} navigable elements (from {len(candidates)} total)")
        
        return top_candidates

    async def _extract_links(self, limit: int = 30) -> List[Dict[str, Any]]:
        # Try multiple selectors for better coverage (including SVG, image buttons, etc.)
        selectors = [
            "a, button, [role='button'], input[type='button'], input[type='submit'], [onclick]",
            "[data-testid*='button'], [data-testid*='action']",
            "svg[data-testid], div[role='button']:not([tabindex='-1'])"
        ]
        
        candidates: List[Dict[str, Any]] = []
        
        # Words that indicate navigation to forms
        form_indicators = ["apply", "application", "register", "registration", "form", "exam", "login", 
                          "signup", "join", "participate", "enroll", "admission", "fill", "start", "begin", 
                          "proceed", "next", "continue", "submit", "online", "proceed", "start", "begin",
                          "new", "fresh", "file", "upload", "verify"]
        
        skip_terms = ["privacy", "terms", "cookie", "faq", "help", "support", "footer", "contact", "about", 
                      "home", "back", "logout", "exit", "close", "share", "print", "download"]

        for selector in selectors:
            locator = self.page.locator(selector)
            count = min(await locator.count(), 100)
            
            for i in range(count):
                try:
                    handle = locator.nth(i)
                    text = _normalize_text(await handle.inner_text())
                    href = await handle.get_attribute("href")
                    
                    if not text or len(text) < 2:
                        continue
                    
                    lower = text.lower()
                    
                    # Skip irrelevant links
                    if any(term in lower for term in skip_terms):
                        continue
                    
                    # Prioritize form-related links
                    is_form_link = any(term in lower for term in form_indicators)
                    priority = 1.0 if is_form_link else 0.5
                    
                    # Check if this candidate already exists
                    exists = any(c["text"].lower() == text.lower() for c in candidates)
                    if exists:
                        continue
                    
                    candidates.append({
                        "index": i, 
                        "text": text[:100], 
                        "href": href or "",
                        "priority": priority,
                        "is_form_link": is_form_link,
                        "selector": selector
                    })
                    
                    if len(candidates) >= limit:
                        break
                except Exception:
                    continue
            
            if len(candidates) >= limit:
                break
        
        # Sort by priority (form-related links first)
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[:limit]
    
    async def _choose_best_element(self, user_intent: str, elements: List[Dict[str, Any]]) -> Optional[int]:
        """AI selection with thought preservation."""
        if not elements: return None
        
        # Log to thought console
        await self.visual.add_thought(f"Choosing from {len(elements)} possible pathways...")
        
        element_descriptions = [f"{i}. [{e['type']}] {e['text']}" for i, e in enumerate(elements[:12])]
        
        prompt = (
            f"Goal: {user_intent}\n"
            f"Page: {await self.page.title()}\n"
            "Options:\n" + "\n".join(element_descriptions) + "\n\n"
            "Task: Return the index of the most relevant element.\n"
            "Rules:\n"
            "- Favor elements related to registration or application.\n"
            "- Return ONLY the number.\n"
            "Answer:"
        )
        
        try:
            resp = self.model.generate_content(prompt)
            match = re.search(r'-?\d+', resp.text)
            if match:
                idx = int(match.group())
                if 0 <= idx < len(elements):
                    return idx
        except: pass
        return 0 # Fallback
    
    async def _click_element_safe(self, element_info: Dict) -> bool:
        """Safely click an element with visuals and multiple fallbacks."""
        selector = element_info.get("selector")
        index = element_info.get("index")
        text = element_info.get("text")
        
        try:
            locator = self.page.locator(selector).nth(index)
            await self.visual.highlight_element(f"{selector} >> nth={index}", "clicking")
            await locator.click(timeout=5000)
            return True
        except Exception as e:
            print(f"[NAV] Primary click failed: {e}")
            
            # Fallback 1: Click by text
            try:
                if text:
                    await self.visual.add_thought(f"Retrying: Clicking '{text}' by text search")
                    await self.page.get_by_text(text, exact=False).first.click(timeout=5000)
                    return True
            except: pass
            
            # Fallback 2: JS Click
            try:
                await self.visual.add_thought("Retrying: Emergency JavaScript click")
                await self.page.evaluate(f"document.querySelectorAll('{selector}')[{index}].click()")
                return True
            except: pass
            
            return False

    async def _reason_with_path(self, reason: str, path: List[str]) -> str:
        """Helper to format the final navigation reason with the path taken."""
        path_str = " -> ".join([p.split('/')[-1] or p for p in path])
        return f"{reason} | Path: {path_str}"

    async def _human_move_mouse(self) -> None:
        """Simulate human-like mouse movements to jitter detection."""
        try:
            viewport = self.page.viewport_size
            if viewport:
                x = random.randint(0, viewport['width'])
                y = random.randint(0, viewport['height'])
                await self.page.mouse.move(x, y, steps=10)
        except: pass

async def find_form_on_page(page: Page) -> bool:
    """Helper to find if any form exists on the current page."""
    # Simplified version for now, could be expanded back if needed
    try:
        inputs = await page.locator('input:visible, textarea:visible, select:visible').count()
        return inputs > 0
    except: return False

async def find_base_url(user_query: str) -> Optional[str]:
    """Starting URL discovery."""
    return None # Placeholder
