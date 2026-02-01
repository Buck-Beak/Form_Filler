"""Debug script to explore eVerify page structure and understand button flows."""

import asyncio
from playwright.async_api import async_playwright
import json


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Open visible browser
        page = await browser.new_page()
        
        print("🔍 Navigating to eVerify URL...")
        await page.goto("https://eportal.incometax.gov.in/iec/foservices/#/pre-login/eVerifyReturn-bl")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Get page structure
        print("\n📄 PAGE STRUCTURE ANALYSIS:")
        print("=" * 60)
        
        # Get all buttons and their text
        buttons = await page.locator("button, [role='button'], input[type='button']").all()
        print(f"\n🔘 Found {len(buttons)} buttons/clickable elements:")
        for i, btn in enumerate(buttons):
            text = await btn.inner_text()
            visible = await btn.is_visible()
            enabled = await btn.is_enabled()
            print(f"   [{i}] {text[:50]} | visible={visible} enabled={enabled}")
        
        # Get all input fields
        inputs = await page.locator("input, textarea, select").all()
        print(f"\n📝 Found {len(inputs)} input fields:")
        for i, inp in enumerate(inputs):
            inp_type = await inp.get_attribute("type")
            placeholder = await inp.get_attribute("placeholder")
            name = await inp.get_attribute("name")
            visible = await inp.is_visible()
            print(f"   [{i}] type={inp_type} name={name} placeholder={placeholder} visible={visible}")
        
        # Get all links
        links = await page.locator("a").all()
        print(f"\n🔗 Found {len(links)} links:")
        for i, link in enumerate(links[:15]):  # Show first 15
            text = await link.inner_text()
            href = await link.get_attribute("href")
            visible = await link.is_visible()
            print(f"   [{i}] {text[:40]} -> {href} visible={visible}")
        
        # Check page content
        page_text = await page.inner_text()
        print(f"\n📜 Page content length: {len(page_text)} chars")
        print("First 500 chars of page:")
        print(page_text[:500])
        
        # Get forms
        forms = await page.locator("form").all()
        print(f"\n📋 Found {len(forms)} form elements")
        
        # Detailed analysis - try clicking buttons to see what happens
        print("\n\n🧪 INTERACTIVE TESTING:")
        print("=" * 60)
        print("Looking for form-related buttons to click...\n")
        
        # Look for specific keywords
        keywords = ["continue", "proceed", "next", "start", "login", "verify", "submit"]
        for btn in buttons[:10]:
            text = (await btn.inner_text()).lower()
            for keyword in keywords:
                if keyword in text:
                    print(f"✨ Found button: '{text}' - clicking it...")
                    await btn.click()
                    await asyncio.sleep(2)
                    
                    # Check if form appeared
                    new_inputs = await page.locator("input, textarea, select").all()
                    print(f"   After click: Found {len(new_inputs)} input fields")
                    
                    # Show form fields if found
                    if len(new_inputs) > 0:
                        print("   Form fields visible:")
                        for inp in new_inputs[:5]:
                            inp_type = await inp.get_attribute("type")
                            placeholder = await inp.get_attribute("placeholder")
                            visible = await inp.is_visible()
                            print(f"      - type={inp_type} placeholder={placeholder} visible={visible}")
                    
                    await asyncio.sleep(1)
                    break
        
        print("\n✅ Manual inspection complete. Browser will stay open.")
        print("   Explore the form, click buttons, and check what appears.")
        print("   Close the browser when done to continue analysis.")
        
        # Keep browser open for manual inspection
        await asyncio.sleep(300)  # 5 minutes
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
