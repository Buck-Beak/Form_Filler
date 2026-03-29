import asyncio
from playwright.async_api import async_playwright
import os
import sys
import subprocess
import time

# Add Form_Filler to path
sys.path.append(os.path.join(os.getcwd(), "Form_Filler"))

from navigation_agent import NavigationAgent
from visual_feedback import VisualFeedback
from session_storage import SessionStorage

async def run_reproduction():
    # Start a local HTTP server in the background
    server_process = subprocess.Popen(
        ["python", "-m", "http.server", "8008"],
        cwd=os.path.join(os.getcwd(), "test_website"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Local server started at http://localhost:8008")
    
    time.sleep(2) # Wait for server to start
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Listen for console logs
            page.on("console", lambda msg: print(f"[PAGE CONSOLE] {msg.text}"))
            
            # Start at step2.html which has the JS buttons
            start_url = "http://localhost:8008/navigation/step2.html"
            print(f"Navigating to {start_url}")
            await page.goto(start_url)
            await asyncio.sleep(2)
            
            print(f"Page Title: {await page.title()}")
            content = await page.content()
            print(f"Content Length: {len(content)}")
            if "glass-card" in content:
                print("SUCCESS: glass-card found in HTML.")
            else:
                print("WARNING: glass-card NOT found in HTML.")
                print(f"Snippet: {content[:500]}")
            
            # Setup agent
            from google.generativeai import GenerativeModel
            # Mocking model for extraction (we just care about the elements found before AI)
            model = None 
            
            visual = VisualFeedback(page)
            storage = SessionStorage()
            agent = NavigationAgent(page, model)
            agent.visual = visual
            agent.session_storage = storage
            
            print("Step 1: Check if JS buttons are extracted...")
            elements = await agent._extract_smart_elements("Apply for registration")
            
            button_texts = [e['text'].lower() for e in elements]
            print(f"Extracted elements: {button_texts}")
            
            selected = None
            for e in elements:
                if "individual" in e['text'].lower():
                    selected = e
                    break
            
            if not selected:
                print("FAILED: Could not find 'Individual' button")
                return

            print(f"Step 2: Clicking '{selected['text']}'...")
            success = await agent._click_element_safe(selected)
            if not success:
                print("FAILED: Click failed")
                return
            
            await asyncio.sleep(2)
            print(f"New URL: {page.url}")
            if "final_form.html" in page.url:
                print("SUCCESS: Navigated to final_form.html")
            else:
                print("FAILED: Did not navigate to final_form.html")

            print("Step 3: Checking form detection...")
            has_form = await agent._has_form()
            if has_form:
                print("SUCCESS: Form detected on final page.")
            else:
                print("FAILED: Form NOT detected on final page.")

            # Step 4: Iframe test
            print("\nStep 4: Testing iframe detection...")
            iframe_html = """
            <html><body>
                <h2>Main Page</h2>
                <iframe src="navigation/final_form.html" name="form_frame"></iframe>
            </body></html>
            """
            with open(os.path.join(os.getcwd(), "test_website", "iframe_test.html"), "w") as f:
                f.write(iframe_html)
            
            await page.goto("http://localhost:8008/iframe_test.html")
            await asyncio.sleep(2)
            
            has_form_iframe = await agent._has_form()
            if has_form_iframe:
                print("SUCCESS: Form detected inside iframe.")
            else:
                print("FAILED: Form NOT detected inside iframe.")
            
            os.remove(os.path.join(os.getcwd(), "test_website", "iframe_test.html"))
            
            await browser.close()
    finally:
        server_process.terminate()
        print("Local server stopped.")

if __name__ == "__main__":
    asyncio.run(run_reproduction())
