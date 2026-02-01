"""
Test the updated navigation agent against eVerify
This tests the improvements:
1. Better link extraction (multiple selectors)
2. Relaxed form detection (looking for form containers)
3. Special handling for income tax portals
4. Blind button click strategy for SPAs
"""

import asyncio
import sys
sys.path.insert(0, ".")

from navigation_agent import NavigationAgent
from browser_utils import launch_browser
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key="YOUR_GEMINI_KEY")  # Will use env var if not set
model = genai.GenerativeModel("gemini-2.5-flash")


async def test_everify_navigation():
    browser = None
    try:
        print("=" * 60)
        print("🧪 Testing eVerify Form Navigation")
        print("=" * 60)
        
        browser = await launch_browser()
        page = await browser.new_page()
        
        nav = NavigationAgent(page, model)
        
        print("\n🚀 Starting navigation from eVerify URL...")
        start_url = "https://eportal.incometax.gov.in/iec/foservices/#/pre-login/eVerifyReturn-bl"
        user_intent = "verify income tax return"
        
        found, final_url, reason = await nav.maps_to_form(start_url, user_intent, max_attempts=5)
        
        print("\n" + "=" * 60)
        print("📊 Results:")
        print("=" * 60)
        print(f"Found Form: {found}")
        print(f"Final URL: {final_url}")
        print(f"Reason: {reason}")
        
        if found:
            print("\n✅ SUCCESS! Form was found.")
            print("🎉 eVerify navigation is working!")
        else:
            print("\n❌ Form not found.")
            print("💡 This might mean:")
            print("   1. Website structure changed")
            print("   2. Anti-bot protection is blocking access")
            print("   3. JavaScript rendering is timing out")
        
        # Take screenshot for debugging
        screenshot_path = "everify_test_screenshot.png"
        await page.screenshot(path=screenshot_path)
        print(f"\n📸 Screenshot saved to: {screenshot_path}")
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if browser:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_everify_navigation())
