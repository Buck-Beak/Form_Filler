"""
Strategy for eVerify and similar portal forms:
1. These are SPAs (Single Page Applications)  
2. They load forms dynamically
3. They need explicit button clicks to reveal the form
4. The form detection should look for indicators, not just input fields

Solution: Add a "blind click" strategy - if no links found,  try clicking any visible button
"""

import asyncio
from playwright.async_api import async_playwright


async def test_everify_blind_click():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")  # Reuse browser
        page = await browser.new_page()
        
        print("🔍 Testing eVerify with blind click strategy...")
        await page.goto("https://eportal.incometax.gov.in/iec/foservices/#/pre-login/eVerifyReturn-bl")
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)
        
        # STRATEGY: If no buttons found, the page might still be loading
        # Try to find ANY visible interactive element
        
        # Get all possible buttons/links in order
        all_clickables = await page.locator(
            "button, [role='button'], a, [onclick], [data-testid*='button'], input[type='submit'], input[type='button']"
        ).all()
        
        print(f"✅ Found {len(all_clickables)} clickable elements")
        
        # Try first few
        for i, elem in enumerate(all_clickables[:5]):
            try:
                text = await elem.inner_text()
                visible = await elem.is_visible()
                enabled = await elem.is_enabled()
                tag = await elem.evaluate("el => el.tagName")
                
                print(f"\n   {i}. <{tag}> visible={visible} enabled={enabled}")
                print(f"      Text: {text[:60]}")
                
                if visible and enabled:
                    print(f"      👆 Attempting to click this...")
                    await elem.click()
                    await asyncio.sleep(2)
                    
                    # Check if form now visible
                    inputs = await page.locator("input:visible").count()
                    print(f"      Result: {inputs} input fields visible")
                    
                    if inputs > 0:
                        print("      ✅ SUCCESS - Form is now visible!")
                        return True
                        
            except Exception as e:
                print(f"      ❌ Error: {e}")
        
        print("\n❌ No success with blind clicking")
        return False


# Run this with a dev browser open: playwright inspect
if __name__ == "__main__":
    # Just print the strategy
    print(__doc__)
