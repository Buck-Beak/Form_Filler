"""Quick diagnostic for eVerify page - shows what's actually there."""

import asyncio
from playwright.async_api import async_playwright
import json


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print("🔍 Loading eVerify page...")
        await page.goto("https://eportal.incometax.gov.in/iec/foservices/#/pre-login/eVerifyReturn-bl")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Check what buttons exist
        buttons = await page.locator("button:visible, [role='button']:visible").all()
        print(f"\n📌 Visible buttons/clickables: {len(buttons)}")
        for i, btn in enumerate(buttons):
            try:
                text = await btn.inner_text()
                is_enabled = await btn.is_enabled()
                print(f"   {i}. {text[:60]} [enabled={is_enabled}]")
            except:
                pass
        
        # Check for form containers
        form_containers = await page.locator("[class*='form'], [class*='Form'], [id*='form']").all()
        print(f"\n📋 Form-like containers: {len(form_containers)}")
        
        # Check for input fields
        inputs = await page.locator("input[visible], textarea[visible], select[visible]").all()
        print(f"\n📝 Input fields: {len(inputs)}")
        for i, inp in enumerate(inputs):
            try:
                inp_type = await inp.get_attribute("type")
                label = await inp.get_attribute("placeholder") or await inp.get_attribute("name")
                print(f"   {i}. type={inp_type} label={label}")
            except:
                pass
        
        # Check page for "Continue" or "Next" buttons specifically
        page_html = await page.content()
        if "continue" in page_html.lower():
            print("\n✅ Found 'continue' button in HTML")
        if "proceed" in page_html.lower():
            print("✅ Found 'proceed' button in HTML")
        if "next" in page_html.lower():
            print("✅ Found 'next' button in HTML")
        if "start" in page_html.lower():
            print("✅ Found 'start' button in HTML")
        
        print("\n🧪 Trying to find and click first visible button...")
        first_btn = await page.locator("button:visible, [role='button']:visible").first
        if await first_btn.is_visible():
            btn_text = await first_btn.inner_text()
            print(f"   Clicking: {btn_text}")
            try:
                await first_btn.click()
                await asyncio.sleep(3)
                
                # Check if form appeared
                new_inputs = await page.locator("input[visible], textarea[visible]").all()
                print(f"   After click: {len(new_inputs)} input fields visible")
                
                if len(new_inputs) > 0:
                    print("   ✅ Form appeared!")
                    for inp in new_inputs[:3]:
                        try:
                            label = await inp.get_attribute("placeholder") or await inp.get_attribute("name")
                            print(f"      - {label}")
                        except:
                            pass
            except Exception as e:
                print(f"   ❌ Click failed: {e}")
        
        print("\n✅ Diagnostic complete")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
