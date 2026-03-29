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

async def run_verification():
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
            
            # Start at step1.html which has a high-priority "Apply" button
            start_url = "http://localhost:8008/navigation/step1.html"
            await page.goto(start_url)
            
            # Setup agent with MOCK model that track calls
            class MockModel:
                def __init__(self):
                    self.call_count = 0
                def generate_content(self, prompt):
                    self.call_count += 1
                    return type('Resp', (), {'text': '0'})()

            mock_model = MockModel()
            visual = VisualFeedback(page)
            agent = NavigationAgent(page, mock_model)
            agent.visual = visual
            
            print("--- Test 1: Confidence Shortcut ---")
            print("Navigating step 1 -> step 2 (should skip AI)")
            # 'Apply for Registration' should have score 2.4 (2.0 form_related * 1.2 button boost)
            success, url, msg = await agent.maps_to_form(start_url, "Apply for registration", max_attempts=2)
            
            print(f"Goal reached: {success}")
            print(f"AI Call Count: {mock_model.call_count}")
            
            if mock_model.call_count == 0:
                print("SUCCESS: AI calls were skipped due to high confidence shortcut!")
            else:
                print(f"FAIL: AI was called {mock_model.call_count} times.")

            print("\n--- Test 2: AI Exhaustion Fallback ---")
            # Force 429 error
            class ExhaustedModel:
                def generate_content(self, prompt):
                    raise Exception("Resource has been exhausted (e.g. check quota). [429]")
            
            agent.model = ExhaustedModel()
            # Start at step2.html (div buttons have lower priority unless specific, let's see)
            # Actually, the div buttons in step2.html might have priority 1.0 or 1.2
            # Let's see if it falls back to first element
            await page.goto("http://localhost:8008/navigation/step2.html")
            
            print("Simulating API [429]. Bot should fallback to heuristics.")
            elements = await agent._extract_smart_elements("Apply")
            # Manually trigger the flow to see if it survives
            try:
                # This should catch the 429 and return the first element
                idx = await agent._choose_best_element("Apply", elements)
                print(f"Selected index after 429: {idx}")
                if idx == 0:
                    print("SUCCESS: Fallback to local heuristics worked!")
                else:
                    print("FAIL: Fallback did not return top candidate.")
            except Exception as e:
                print(f"FAIL: System crashed on 429: {e}")

            await browser.close()
    finally:
        server_process.terminate()
        print("Local server stopped.")

if __name__ == "__main__":
    asyncio.run(run_verification())
