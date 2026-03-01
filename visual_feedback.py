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
        self.thoughts = []
    
    async def inject_visual_styles(self):
        """Inject CSS styles for visual feedback"""
        if self._inject_styles_done:
            return
        
        try:
            await self.page.evaluate("""
                () => {
                    const existing = document.getElementById('bot-visual-feedback-styles');
                    if (existing) existing.remove();
                    
                    const style = document.createElement('style');
                    style.id = 'bot-visual-feedback-styles';
                    style.textContent = `
                        :root {
                            --bot-accent: #38bdf8;
                            --bot-success: #22c55e;
                            --bot-warning: #f59e0b;
                            --bot-bg: rgba(15, 23, 42, 0.9);
                            --bot-border: rgba(56, 189, 248, 0.3);
                        }

                        .bot-page-active {
                            outline: 4px solid var(--bot-accent) !important;
                            outline-offset: -4px !important;
                        }
                        
                        .bot-element-considering {
                            outline: 3px solid var(--bot-warning) !important;
                            outline-offset: 2px !important;
                            background-color: rgba(245, 158, 11, 0.1) !important;
                            transition: all 0.3s ease;
                        }
                        
                        .bot-element-clicking {
                            outline: 4px solid var(--bot-success) !important;
                            outline-offset: 2px !important;
                            background-color: rgba(34, 197, 94, 0.2) !important;
                            animation: bot-click-pulse 0.6s ease-out;
                        }
                        
                        /* Thought Log Overlay */
                        .bot-thought-overlay {
                            position: fixed;
                            bottom: 20px;
                            right: 20px;
                            width: 350px;
                            max-height: 400px;
                            background: var(--bot-bg);
                            backdrop-filter: blur(12px);
                            border: 1px solid var(--bot-border);
                            border-radius: 12px;
                            color: white;
                            z-index: 1000000;
                            display: flex;
                            flex-direction: column;
                            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                            font-family: 'Inter', sans-serif;
                            overflow: hidden;
                            animation: bot-slide-up 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                        }

                        .bot-thought-header {
                            padding: 12px 16px;
                            background: rgba(56, 189, 248, 0.1);
                            border-bottom: 1px solid var(--bot-border);
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                        }

                        .bot-status-indicator {
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            font-weight: 600;
                            font-size: 13px;
                            color: var(--bot-accent);
                        }

                        .bot-spinner {
                            width: 12px;
                            height: 12px;
                            border: 2px solid var(--bot-accent);
                            border-top-color: transparent;
                            border-radius: 50%;
                            animation: bot-spin 0.8s linear infinite;
                        }

                        .bot-thought-list {
                            padding: 12px;
                            overflow-y: auto;
                            flex-grow: 1;
                            font-size: 13px;
                            line-height: 1.5;
                        }

                        .bot-thought-item {
                            margin-bottom: 10px;
                            padding-left: 12px;
                            border-left: 2px solid rgba(255,255,255,0.1);
                            animation: bot-fade-in 0.3s ease;
                        }

                        .bot-thought-item.current {
                            border-left-color: var(--bot-accent);
                            color: var(--bot-accent);
                        }

                        @keyframes bot-click-pulse {
                            0% { transform: scale(1); }
                            50% { transform: scale(1.02); }
                            100% { transform: scale(1); }
                        }

                        @keyframes bot-slide-up {
                            from { transform: translateY(20px); opacity: 0; }
                            to { transform: translateY(0); opacity: 1; }
                        }

                        @keyframes bot-fade-in {
                            from { opacity: 0; }
                            to { opacity: 1; }
                        }

                        @keyframes bot-spin {
                            to { transform: rotate(360deg); }
                        }
                    `;
                    document.head.appendChild(style);
                }
            """)
            self._inject_styles_done = True
        except Exception as e:
            print(f"[VisualFeedback] ⚠️ Injection failed: {e}")

    async def add_thought(self, thought: str):
        """Add a thought to the dynamic on-page log"""
        self.thoughts.append(thought)
        await self.inject_visual_styles()
        try:
            await self.page.evaluate("""
                (thought) => {
                    let overlay = document.getElementById('bot-thought-overlay');
                    if (!overlay) {
                        overlay = document.createElement('div');
                        overlay.id = 'bot-thought-overlay';
                        overlay.className = 'bot-thought-overlay';
                        overlay.innerHTML = `
                            <div class="bot-thought-header">
                                <div class="bot-status-indicator">
                                    <div class="bot-spinner"></div>
                                    <span>ANTIGRAVITY ACTIVE</span>
                                </div>
                            </div>
                            <div id="bot-thought-list" class="bot-thought-list"></div>
                        `;
                        document.body.appendChild(overlay);
                    }
                    
                    const list = document.getElementById('bot-thought-list');
                    const items = list.querySelectorAll('.bot-thought-item');
                    items.forEach(i => i.classList.remove('current'));
                    
                    const item = document.createElement('div');
                    item.className = 'bot-thought-item current';
                    item.textContent = thought;
                    list.appendChild(item);
                    list.scrollTop = list.scrollHeight;
                    
                    // Keep last 10 thoughts
                    while (list.children.length > 10) {
                        list.removeChild(list.firstChild);
                    }
                }
            """, thought)
        except Exception as e:
            print(f"[VisualFeedback] Error adding thought: {e}")

    async def highlight_element(self, selector: str, type: str = "considering"):
        """Highlight an element with visual styles"""
        await self.inject_visual_styles()
        try:
            await self.page.evaluate(f"""
                (selector) => {{
                    const el = document.querySelector(selector);
                    if (el) {{
                        el.classList.add('bot-element-{type}');
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }}
                }}
            """, selector)
        except: pass

    async def clear_highlights(self):
        """Remove all visual feedback highlights"""
        try:
            await self.page.evaluate("""
                () => {
                    document.querySelectorAll('.bot-element-considering, .bot-element-clicking')
                        .forEach(el => {
                            el.classList.remove('bot-element-considering');
                            el.classList.remove('bot-element-clicking');
                        });
                }
            """)
        except: pass

    async def show_form_found(self):
        await self.add_thought("🎯 Target form detected! Preparing to fill...")

    async def show_filling_field(self, name: str, value: str):
        await self.add_thought(f"✍️ Filling field \"{name}\" with \"{value}\"")
    
    async def show_clicking(self, text: str):
        await self.add_thought(f"👆 Clicking on \"{text}\"")

    async def show_thinking(self, message: str):
        await self.add_thought(f"🤔 {message}")
