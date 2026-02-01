"""
Visual Feedback System - Provides AntiGravity-style visual feedback for navigation
Shows users what the bot is doing with highlights and overlays
"""
import asyncio
from typing import Optional
from playwright.async_api import Page


class VisualFeedback:
    """Provides visual feedback during navigation like AntiGravity browser"""
    
    def __init__(self, page: Page):
        self.page = page
        self._inject_styles_done = False
    
    async def inject_visual_styles(self):
        """Inject CSS styles for visual feedback"""
        if self._inject_styles_done:
            return
        
        try:
            await self.page.evaluate("""
                () => {
                    // Remove existing styles if any
                    const existing = document.getElementById('bot-visual-feedback-styles');
                    if (existing) existing.remove();
                    
                    const style = document.createElement('style');
                    style.id = 'bot-visual-feedback-styles';
                    style.textContent = `
                        /* Highlight current page with blue border */
                        .bot-page-active {
                            outline: 4px solid #0066ff !important;
                            outline-offset: -4px !important;
                            animation: bot-pulse 2s infinite;
                        }
                        
                        /* Element being considered */
                        .bot-element-considering {
                            outline: 3px solid #ffaa00 !important;
                            outline-offset: 2px !important;
                            background-color: rgba(255, 170, 0, 0.1) !important;
                            animation: bot-shimmer 1s infinite;
                        }
                        
                        /* Element being clicked */
                        .bot-element-clicking {
                            outline: 4px solid #00ff00 !important;
                            outline-offset: 2px !important;
                            background-color: rgba(0, 255, 0, 0.2) !important;
                            animation: bot-click-flash 0.5s;
                        }
                        
                        /* Navigation overlay */
                        .bot-overlay {
                            position: fixed;
                            top: 10px;
                            right: 10px;
                            background: rgba(0, 0, 0, 0.85);
                            color: white;
                            padding: 15px 20px;
                            border-radius: 10px;
                            font-family: Arial, sans-serif;
                            font-size: 14px;
                            z-index: 999999;
                            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                            max-width: 300px;
                            animation: bot-slide-in 0.3s;
                        }
                        
                        .bot-overlay-title {
                            font-weight: bold;
                            font-size: 16px;
                            margin-bottom: 8px;
                            color: #0066ff;
                        }
                        
                        .bot-overlay-action {
                            margin: 5px 0;
                            padding-left: 20px;
                            position: relative;
                        }
                        
                        .bot-overlay-action::before {
                            content: '→';
                            position: absolute;
                            left: 0;
                            color: #00ff00;
                        }
                        
                        /* Animations */
                        @keyframes bot-pulse {
                            0%, 100% { outline-color: #0066ff; }
                            50% { outline-color: #0099ff; }
                        }
                        
                        @keyframes bot-shimmer {
                            0%, 100% { background-color: rgba(255, 170, 0, 0.1); }
                            50% { background-color: rgba(255, 170, 0, 0.3); }
                        }
                        
                        @keyframes bot-click-flash {
                            0% { background-color: rgba(0, 255, 0, 0.5); }
                            100% { background-color: rgba(0, 255, 0, 0.1); }
                        }
                        
                        @keyframes bot-slide-in {
                            from {
                                transform: translateX(100%);
                                opacity: 0;
                            }
                            to {
                                transform: translateX(0);
                                opacity: 1;
                            }
                        }
                    `;
                    document.head.appendChild(style);
                }
            """)
            self._inject_styles_done = True
            print("[VisualFeedback] ✅ Injected visual styles")
        except Exception as e:
            print(f"[VisualFeedback] ⚠️ Failed to inject styles: {e}")
    
    async def highlight_page(self):
        """Highlight the current page with blue border"""
        await self.inject_visual_styles()
        try:
            await self.page.evaluate("""
                () => {
                    document.body.classList.add('bot-page-active');
                }
            """)
        except Exception as e:
            print(f"[VisualFeedback] Error highlighting page: {e}")
    
    async def remove_page_highlight(self):
        """Remove page highlight"""
        try:
            await self.page.evaluate("""
                () => {
                    document.body.classList.remove('bot-page-active');
                }
            """)
        except Exception as e:
            print(f"[VisualFeedback] Error removing page highlight: {e}")
    
    async def highlight_element(self, selector: str, highlight_type: str = "considering"):
        """
        Highlight an element
        
        Args:
            selector: CSS selector for element
            highlight_type: 'considering' (yellow) or 'clicking' (green)
        """
        await self.inject_visual_styles()
        
        css_class = f"bot-element-{highlight_type}"
        
        try:
            await self.page.evaluate(f"""
                (selector) => {{
                    const element = document.querySelector(selector);
                    if (element) {{
                        element.classList.add('{css_class}');
                        element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        
                        // Remove highlight after a delay
                        setTimeout(() => {{
                            element.classList.remove('{css_class}');
                        }}, {2000 if highlight_type == 'considering' else 1000});
                    }}
                }}
            """, selector)
            await asyncio.sleep(0.3)  # Let user see the highlight
        except Exception as e:
            print(f"[VisualFeedback] Error highlighting element: {e}")
    
    async def show_action_overlay(self, action: str, details: Optional[str] = None):
        """
        Show an overlay describing current action
        
        Args:
            action: Main action (e.g., "Navigating", "Clicking button", "Filling form")
            details: Additional details (e.g., button text, field name)
        """
        await self.inject_visual_styles()
        
        details_html = f"<div class='bot-overlay-action'>{details}</div>" if details else ""
        
        try:
            await self.page.evaluate(f"""
                (action, details) => {{
                    // Remove existing overlay
                    const existing = document.getElementById('bot-action-overlay');
                    if (existing) existing.remove();
                    
                    // Create new overlay
                    const overlay = document.createElement('div');
                    overlay.id = 'bot-action-overlay';
                    overlay.className = 'bot-overlay';
                    overlay.innerHTML = `
                        <div class='bot-overlay-title'>🤖 Bot Action</div>
                        <div class='bot-overlay-action'>${{action}}</div>
                        ${{details || ''}}
                    `;
                    document.body.appendChild(overlay);
                    
                    // Auto-remove after 5 seconds
                    setTimeout(() => {{
                        if (overlay.parentElement) {{
                            overlay.remove();
                        }}
                    }}, 5000);
                }}
            """, action, details_html)
        except Exception as e:
            print(f"[VisualFeedback] Error showing overlay: {e}")
    
    async def show_thinking(self, message: str):
        """Show 'thinking' state"""
        await self.show_action_overlay("🤔 Thinking...", message)
    
    async def show_navigating(self, target: str):
        """Show navigation action"""
        await self.show_action_overlay("🧭 Navigating", f"Looking for: {target}")
    
    async def show_clicking(self, element_text: str):
        """Show clicking action"""
        await self.show_action_overlay("👆 Clicking", f"Element: {element_text[:50]}")
    
    async def show_form_found(self):
        """Show form found success"""
        await self.show_action_overlay("✅ Form Found!", "Starting to fill fields...")
    
    async def show_filling_field(self, field_name: str, value: str):
        """Show field being filled"""
        await self.show_action_overlay("✍️ Filling Field", f"{field_name}: {value[:30]}")
    
    async def remove_overlay(self):
        """Remove action overlay"""
        try:
            await self.page.evaluate("""
                () => {
                    const overlay = document.getElementById('bot-action-overlay');
                    if (overlay) overlay.remove();
                }
            """)
        except Exception as e:
            print(f"[VisualFeedback] Error removing overlay: {e}")
    
    async def flash_element_click(self, element_handle):
        """Flash an element when clicking it"""
        try:
            await element_handle.evaluate("""
                (element) => {
                    element.classList.add('bot-element-clicking');
                    setTimeout(() => {
                        element.classList.remove('bot-element-clicking');
                    }, 500);
                }
            """)
        except Exception as e:
            print(f"[VisualFeedback] Error flashing element: {e}")
