import asyncio
import sys
import os
from playwright.async_api import async_playwright

# Add project root to sys.path
project_root = r"c:\Users\abhij\OneDrive\Desktop\finalYearProject\Form_Filler"
sys.path.append(project_root)

from navigation_agent import NavigationAgent
import google.generativeai as genai
from config import GEMINI_API_KEY

async def test_navigation():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        agent = NavigationAgent(
            playwright_page=page,
            gemini_model=model
        )
        
        print("Testing Navigation on Local Testbed...")
        # Point to the local test website
        success, url, reason = await agent.maps_to_form("http://localhost:8000/index.html", "admission form")
        
        print(f"Result: Success={success}")
        print(f"URL: {url}")
        print(f"Reason: {reason}")
        
        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_navigation())
