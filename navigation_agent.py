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

    def __init__(self, playwright_page: Page, gemini_model: genai.GenerativeModel):
        self.page = playwright_page
        self.model = gemini_model
        self.visual = VisualFeedback(playwright_page)
        self.session_storage = SessionStorage()
        self.current_session_steps = []
        self.start_time = None

    async def maps_to_form(self, start_url: str, user_intent: str, max_attempts: int = 4) -> Tuple[bool, str, str]:
        """
        Enhanced Look-Think-Act loop to reach a form page with visual feedback and learning.
        Checks for form FIRST before attempting navigation.

        Returns: (found_form, final_url, reason_with_path)
        """
        self.start_time = datetime.now()
        visited: set[str] = set()
        path: List[str] = []
        
        # Check if we've successfully navigated here before
        previous_sessions = self.session_storage.get_successful_paths(start_url, user_intent)
        if previous_sessions:
            print(f"[NAV] 📚 Found {len(previous_sessions)} previous successful sessions")
            # Try to replay successful path
            replay_success = await self._replay_successful_path(previous_sessions[0], user_intent)
            if replay_success:
                return True, self.page.url, "Replayed successful navigation from history"

        # Initialize visual feedback
        await self.visual.inject_visual_styles()
        await self.visual.highlight_page()
        await self.visual.show_navigating(user_intent)

        # Navigate to start URL
        try:
            await self.page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)  # Let page render
            self._record_step(start_url, "navigate", "Initial page load")
        except Exception as e:
            print(f"[NAV] Failed to load start URL: {e}")
            await self._save_failed_session(start_url, user_intent, str(e))
            return False, start_url, f"Failed to load start URL: {e}"

        # Check for login page at start
        if await self._is_login_page():
            print("[NAV] 🔐 Login page detected at start")
            self._record_step(self.page.url, "login_detected", "Login required")
            await self.visual.show_action_overlay("🔐 Login Required", "Please login manually")
            # Don't save as failed - login is a valid state
            return False, self.page.url, "Login page detected - please login manually and retry"

        # Special handling for known SPAs (income tax, etc.)
        if "eportal.incometax.gov.in" in start_url or "incometax.gov.in" in start_url:
            print("[NAV] 🏛️ Income Tax portal detected - using special SPA navigation")
            spa_result = await self._handle_spa_navigation(user_intent)
            if spa_result:
                await self._save_successful_session(start_url, user_intent, self.page.url)
                return True, self.page.url, self._reason_with_path("Form found in SPA", path)

        # Main navigation loop
        for attempt in range(1, max_attempts + 1):
            current_url = self.page.url
            path.append(current_url)
            print(f"\n[NAV] ━━━ Attempt {attempt}/{max_attempts} ━━━")
            print(f"[NAV] Current URL: {current_url}")
            
            if current_url in visited:
                print("[NAV] ⚠️ Loop detected - already visited this page")
                await self._save_failed_session(start_url, user_intent, "Loop detected")
                return False, current_url, self._reason_with_path("Loop detected; stopping navigation", path)
            
            visited.add(current_url)

            # Check for blocking/CAPTCHA
            blocked_reason = await self._is_blocked()
            if blocked_reason:
                await self._save_failed_session(start_url, user_intent, blocked_reason)
                raise NavigationBlockedError(blocked_reason)

            # Check for login page
            if await self._is_login_page():
                print("[NAV] 🔐 Login page detected during navigation")
                self._record_step(current_url, "login_detected", "Login required")
                await self.visual.show_action_overlay("🔐 Login Required", "Please login manually")
                return False, current_url, self._reason_with_path("Login page detected - please login manually", path)

            # PRIMARY: Check if form is already present on this page
            await self.visual.show_thinking("Checking for forms on page...")
            if await self._has_form():
                print(f"[NAV] ✅ Form found on page {attempt}!")
                await self.visual.show_form_found()
                self._record_step(current_url, "form_found", "Form detected")
                await self._save_successful_session(start_url, user_intent, current_url)
                return True, current_url, self._reason_with_path("Form detected on page", path)
            
            # Extract and analyze clickable elements
            await self.visual.show_thinking("Analyzing page for navigation options...")
            links = await self._extract_smart_elements(user_intent, limit=30)
            
            if not links:
                print(f"[NAV] ⚠️ No navigable elements found on page {attempt}")
                
                # FALLBACK: Try intelligent button clicking for SPAs
                if await self._try_spa_blind_clicks(user_intent):
                    await self._save_successful_session(start_url, user_intent, self.page.url)
                    return True, self.page.url, self._reason_with_path("Form found after SPA button clicks", path)
                
                # Last resort: wait and try form detection again
                await asyncio.sleep(2)
                if await self._has_form():
                    await self._save_successful_session(start_url, user_intent, self.page.url)
                    return True, current_url, self._reason_with_path("Form detected after delay", path)
                
                await self._save_failed_session(start_url, user_intent, "No navigable elements found")
                return False, current_url, self._reason_with_path("No navigable links found and no form detected", path)

            # Use AI to choose best link
            choice = await self._choose_best_element(user_intent, links)
            if choice is None or choice < 0 or choice >= len(links):
                print(f"[NAV] ⚠️ AI could not select a viable element from {len(links)} options")
                await self._save_failed_session(start_url, user_intent, "AI failed to select link")
                return False, current_url, self._reason_with_path("AI did not select a viable link", path)

            element_info = links[choice]
            print(f"\n[NAV] 👆 Selected element #{element_info['index']}")
            print(f"[NAV]    Text: {element_info['text'][:60]}")
            print(f"[NAV]    Type: {element_info['type']}")
            
            # Show visual feedback
            await self.visual.show_clicking(element_info['text'])
            
            # Click the element with visual feedback
            try:
                success = await self._click_element_safe(element_info)
                if not success:
                    print(f"[NAV] ⚠️ Click failed, trying next element")
                    continue
                
                self._record_step(self.page.url, "click", element_info['text'])
                
                # Wait for navigation/page load
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=20000)
                except PlaywrightTimeoutError:
                    print(f"[NAV] ⚠️ Page load timeout (networkidle not reached)")
                    # Continue anyway, page might still be usable
                
                await asyncio.sleep(random.uniform(2, 4))  # Human-like delay
                await self.visual.highlight_page()
                
            except PlaywrightTimeoutError:
                print(f"[NAV] ⚠️ Navigation timeout, retrying...")
                continue
            except Exception as exc:
                print(f"[NAV] ⚠️ Click failed: {exc}")
                continue

        # Max attempts reached
        await self._save_failed_session(start_url, user_intent, "Max attempts reached")
        return False, self.page.url, self._reason_with_path("Max attempts reached without finding form", path)
    
    # ═══════════════════════════════════════════════════════════════
    # Session Management Methods
    # ═══════════════════════════════════════════════════════════════
    
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
        print(f"[Session] ✅ Saved successful session")
    
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
        print(f"[Session] ❌ Saved failed session: {error}")
    
    async def _replay_successful_path(self, previous_session: Dict, user_intent: str) -> bool:
        """Try to replay a previously successful navigation path"""
        print(f"[NAV] 🔄 Attempting to replay successful path from previous session")
        
        steps = previous_session.get('steps_taken', [])
        for i, step in enumerate(steps):
            if step.get('action') == 'click':
                print(f"[NAV] 🔄 Replaying step {i+1}/{len(steps)}: {step.get('details', '')}")
                await self.visual.show_action_overlay("🔄 Replaying", f"Step {i+1}: {step.get('details', '')[:40]}")
                
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
                            print("[NAV] ✅ Form found during replay!")
                            return True
                except Exception as e:
                    print(f"[NAV] ⚠️ Replay step failed: {e}")
                    # Continue to next step
                    continue
        
        # Check final result
        if await self._has_form():
            print("[NAV] ✅ Form found after full replay!")
            return True
        
        print("[NAV] ⚠️ Replay did not reach form, falling back to normal navigation")
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # Detection Methods
    # ═══════════════════════════════════════════════════════════════
    
    async def _is_login_page(self) -> bool:
        """Detect if current page is a login page"""
        try:
            result = await self.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    const html = document.body.innerHTML.toLowerCase();
                    
                    // Check for common login indicators
                    const loginKeywords = [
                        'sign in', 'signin', 'log in', 'login', 
                        'user id', 'username', 'password', 'enter password',
                        'forgot password', 'remember me', 'keep me signed in'
                    ];
                    
                    const hasLoginKeyword = loginKeywords.some(kw => text.includes(kw) || html.includes(kw));
                    
                    // Check for password field
                    const passwordFields = document.querySelectorAll('input[type="password"]').length;
                    
                    // Check for login-related buttons
                    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                    const hasLoginButton = buttons.some(btn => {
                        const btnText = (btn.textContent || btn.value || '').toLowerCase();
                        return btnText.includes('login') || btnText.includes('sign in') || btnText.includes('log in');
                    });
                    
                    // It's a login page if:
                    // - Has password field AND login keyword/button
                    // - Or has multiple login indicators
                    const isLogin = (passwordFields > 0 && (hasLoginKeyword || hasLoginButton)) ||
                                   (passwordFields > 0 && hasLoginButton);
                    
                    return {
                        isLogin,
                        passwordFields,
                        hasLoginKeyword,
                        hasLoginButton
                    };
                }
            """)
            
            is_login = result.get('isLogin', False)
            if is_login:
                print(f"[NAV] 🔐 Login page detected (password fields: {result.get('passwordFields')}, "
                      f"keywords: {result.get('hasLoginKeyword')}, button: {result.get('hasLoginButton')})")
                # Mark current step as login page
                if self.current_session_steps:
                    self.current_session_steps[-1]['is_login_page'] = True
            
            return is_login
            
        except Exception as e:
            print(f"[NAV] Error detecting login page: {e}")
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
                print(f"[FormDetection] ✅ Found form with {input_count} inputs, {form_containers} form containers")
            else:
                print(f"[FormDetection] ❌ No form detected (inputs: {input_count}, containers: {form_containers})")
            
            return has_form
            
        except Exception as e:
            print(f"[NAV] Form detection error: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════
    # SPA and Smart Navigation Methods
    # ═══════════════════════════════════════════════════════════════
    
    async def _handle_spa_navigation(self, user_intent: str) -> bool:
        """Special handling for Single Page Applications (React, Vue, Angular)"""
        print("[NAV] 🎯 Using SPA-specific navigation...")
        
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
                            print(f"[NAV] 🎯 Found SPA button: {btn_text[:40]}")
                            await self.visual.show_clicking(btn_text)
                            
                            await btn.click()
                            await asyncio.sleep(3)  # SPAs need time to render
                            
                            if await self._has_form():
                                print(f"[NAV] ✅ Form found after SPA button click!")
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
        print("[NAV] 🎯 Trying intelligent button clicks for SPA...")
        
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
            
            print(f"[NAV] 👆 Trying: {element.get('text', '')[:40]} (score: {element.get('score')})")
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
                            print(f"[NAV] ✅ Form found after blind click!")
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
        print("[NAV] 🔍 Extracting navigable elements...")
        
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
        print(f"[NAV] 📋 Found {len(top_candidates)} navigable elements (from {len(candidates)} total)")
        
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
        """
        Enhanced AI-powered element selection
        Uses Gemini to choose the most relevant element for the user's intent
        """
        if not elements:
            return None
        
        # If we have highly relevant form elements, prioritize them
        form_elements = [e for e in elements if e.get("is_form_link", False) and e.get("priority", 0) > 1.5]
        if form_elements:
            print(f"[NAV] 🎯 Found {len(form_elements)} high-priority form elements, selecting first")
            return form_elements[0]["index"]
        
        # Prepare element list for AI
        element_descriptions = []
        for i, elem in enumerate(elements[:12]):  # Show top 12 to AI
            type_label = elem.get('type', 'link')
            priority_indicator = "⭐" if elem.get('is_form_link') else "•"
            element_descriptions.append(
                f"{i}. {priority_indicator} [{type_label}] {elem['text']}"
            )
        
        # Create AI prompt
        prompt = (
            "You are helping navigate to find a specific form on a website.\n\n"
            f"🎯 User's Goal: {user_intent}\n"
            f"📄 Current Page: {await self.page.title()}\n"
            f"🌐 Current URL: {self.page.url}\n\n"
            "Available Elements to Click (⭐ = likely form-related):\n" + 
            "\n".join(element_descriptions) + "\n\n"
            "TASK: Which element should I click to reach the form?\n"
            "RULES:\n"
            "- Prioritize elements marked with ⭐\n"
            "- Look for words like 'apply', 'register', 'form', 'start', 'new'\n"
            "- Avoid 'home', 'back', 'help', 'contact', 'logout'\n"
            "- Return ONLY the index number (0-11)\n"
            "- If none seem relevant, return -1\n\n"
            "Your answer (just the number):"
        )
        
        try:
            resp = self.model.generate_content(prompt)
            raw = (resp.text or "").strip()
            
            # Extract number from response
            match = re.search(r'-?\d+', raw)
            if match:
                idx = int(match.group())
                if 0 <= idx < len(elements):
                    selected = elements[idx]
                    print(f"[NAV] 🤖 AI selected element #{idx}:")
                    print(f"[NAV]    Type: {selected.get('type')}")
                    print(f"[NAV]    Text: {selected['text'][:60]}")
                    print(f"[NAV]    Priority: {selected.get('priority', 0):.2f}")
                    return selected["index"]
                elif idx == -1:
                    print("[NAV] 🤖 AI determined no relevant elements")
                    return None
        except Exception as exc:
            print(f"[NAV] ⚠️ AI selection failed: {exc}")
        
        # Fallback: Choose highest priority element
        if elements:
            highest_priority = max(elements, key=lambda x: x.get('priority', 0))
            print(f"[NAV] 🔄 Fallback: Selecting highest priority element")
            return highest_priority["index"]
        
        return None
    
    async def _click_element_safe(self, element_info: Dict) -> bool:
        """
        Safely click an element with multiple fallback strategies
        Shows visual feedback during click
        
        Returns: True if click succeeded, False otherwise
        """
        selector = element_info.get('selector', '')
        index = element_info.get('index', 0)
        element_type = element_info.get('type', 'unknown')
        text = element_info.get('text', '')
        
        print(f"[NAV] 🖱️ Attempting to click {element_type} element: {text[:40]}")
        
        # Strategy 1: Try with the original selector and index
        try:
            locator = self.page.locator(f"{selector}:visible").nth(index)
            if await locator.count() > 0:
                # Scroll into view
                await locator.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                
                # Show visual feedback
                try:
                    await self.visual.flash_element_click(locator)
                except:
                    pass
                
                # Human-like mouse movement
                await self._human_move_mouse()
                
                # Click
                await locator.click()
                print(f"[NAV] ✅ Click successful (strategy 1)")
                return True
        except Exception as e:
            print(f"[NAV] ⚠️ Strategy 1 failed: {e}")
        
        # Strategy 2: Try finding by text
        if text:
            try:
                locator = self.page.get_by_text(text, exact=False).first
                if await locator.count() > 0:
                    await locator.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    await self._human_move_mouse()
                    await locator.click()
                    print(f"[NAV] ✅ Click successful (strategy 2: by text)")
                    return True
            except Exception as e:
                print(f"[NAV] ⚠️ Strategy 2 failed: {e}")
        
        # Strategy 3: Try clicking any visible element matching the selector
        try:
            locator = self.page.locator(f"{selector}:visible").first
            if await locator.count() > 0:
                await locator.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                await self._human_move_mouse()
                await locator.click()
                print(f"[NAV] ✅ Click successful (strategy 3: first visible)")
                return True
        except Exception as e:
            print(f"[NAV] ⚠️ Strategy 3 failed: {e}")
        
        # Strategy 4: JavaScript click as last resort
        if text:
            try:
                await self.page.evaluate(f"""
                    (text) => {{
                        const elements = Array.from(document.querySelectorAll('a, button, [role="button"]'));
                        const target = elements.find(el => 
                            el.textContent.trim().toLowerCase().includes(text.toLowerCase())
                        );
                        if (target) {{
                            target.click();
                            return true;
                        }}
                        return false;
                    }}
                """, text)
                print(f"[NAV] ✅ Click successful (strategy 4: JavaScript)")
                return True
            except Exception as e:
                print(f"[NAV] ⚠️ Strategy 4 failed: {e}")
        
        print(f"[NAV] ❌ All click strategies failed")
        return False

    async def _choose_link(self, user_intent: str, links: List[Dict[str, Any]]) -> Optional[int]:
        if not links:
            return None
        
        # If we have form-specific links, prioritize them
        form_links = [l for l in links if l.get("is_form_link", False)]
        if form_links:
            # Use top form link if available
            print(f"[NAV] Found {len(form_links)} form-related links, selecting first")
            return form_links[0]["index"]
        
        prompt_links = [
            f"{i}. {item['text']} ({'form-related' if item.get('is_form_link') else 'other'})" 
            for i, item in enumerate(links[:10])
        ]
        prompt = (
            "You are helping a user navigate to find an application/registration form.\n"
            f"User Goal: {user_intent}\n"
            f"Current Page: {await self.page.title()}\n\n"
            "Available Links (ranked by relevance):\n" + "\n".join(prompt_links) + "\n\n"
            "Which link MOST LIKELY leads to the application/registration form for: " + user_intent + "?\n"
            "Return ONLY the index number (0-9). If none seem relevant, return -1."
        )

        try:
            resp = self.model.generate_content(prompt)
            raw = (resp.text or "").strip()
            match = re.search(r'-?\d+', raw)
            if match:
                idx = int(match.group())
                if 0 <= idx < len(links):
                    print(f"[NAV] AI selected link {idx}: {links[idx]['text']}")
                    return links[idx]["index"]
        except Exception as exc:
            print(f"[NAV] Gemini link selection failed: {exc}")
        
        # Fallback: return first form link or first link
        if form_links:
            return form_links[0]["index"]
        return links[0]["index"] if links else None

    async def _click_link(self, index: int) -> None:
        # Try using the generic selector first
        locators = [
            self.page.locator("a, button"),
            self.page.locator("button, [role='button']"),
            self.page.locator("[onclick], [data-testid*='button']")
        ]
        
        for locator in locators:
            try:
                if await locator.count() > index:
                    element = locator.nth(index)
                    if await element.is_visible():
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        return
            except Exception:
                continue
        
        # Fallback: try direct index access
        try:
            all_clickable = await self.page.locator("a, button, [role='button']").all()
            if index < len(all_clickable):
                await all_clickable[index].click()
        except Exception as e:
            print(f"[NAV] Click failed for index {index}: {e}")

    async def _human_move_mouse(self) -> None:
        try:
            box = await self.page.evaluate(
                """
                () => {
                    const w = window.innerWidth;
                    const h = window.innerHeight;
                    return {w, h};
                }
                """
            )
            w, h = box.get("w", 800), box.get("h", 600)
            x1 = random.randint(0, int(w * 0.3))
            y1 = random.randint(0, int(h * 0.3))
            x2 = random.randint(int(w * 0.7), w)
            y2 = random.randint(int(h * 0.7), h)
            await self.page.mouse.move(x1, y1, steps=5)
            await self.page.mouse.move(x2, y2, steps=5)
        except Exception:
            # If mouse move fails, ignore to avoid blocking
            pass

    @staticmethod
    def _reason_with_path(reason: str, path: List[str]) -> str:
        path_str = " -> ".join(path[-5:])  # keep last few hops for brevity
        return f"{reason}. Path: {path_str}"


async def find_form_on_page(page: Page) -> bool:
    """Try to find if any form exists on the current page, including React/Vue forms."""
    try:
        # Check for traditional HTML forms
        form_count = await page.evaluate("() => document.querySelectorAll('form').length")
        if form_count > 0:
            print(f"[FormFinder] Found {form_count} HTML forms on page")
            return True
        
        # Check for form-like elements (inputs, textareas, selects)
        input_count = await page.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], textarea, select');
                const visible = Array.from(inputs).filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
                return visible.length;
            }
        """)
        
        if input_count > 2:
            print(f"[FormFinder] Found {input_count} visible form inputs on page")
            return True
        
        # Check page content for form keywords
        page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        form_keywords = ['fill the form', 'application form', 'registration', 'personal details', 
                        'entrance', 'exam', 'submit your', 'required information']
        
        if any(keyword in page_text for keyword in form_keywords):
            print(f"[FormFinder] Found form keywords in page content")
            return True
        
        return False
    except Exception as e:
        print(f"[FormFinder] Error checking for form: {e}")
        return False


async def find_base_url(user_query: str) -> Optional[str]:
    """Simple DuckDuckGo HTML search to get a starting URL."""
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = requests.get("https://duckduckgo.com/html/", params={"q": user_query}, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and href.startswith("http"):
                return href
    except Exception:
        return None
    return None
