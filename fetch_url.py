from playwright.sync_api import sync_playwright
import google.generativeai as genai
import os
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
model = genai.GenerativeModel("gemini-2.5-flash")
def find_base_url(query):
    prompt = f"""
    The user wants to fill a government form or use a service: "{query}".
    Identify the official website URL where this can be done. Return only the URL.
    """
    resp = model.generate_content(prompt)
    return resp.text.strip()

def navigate_to_epay_tax():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # set True later
        page = browser.new_page()
        page.goto("https://www.incometax.gov.in/iec/foportal/")
        page.wait_for_load_state("networkidle")

        # Click the 'e-Pay Tax' link in the homepage menu
        page.click("text=e-Pay Tax")

        # Wait for the navigation to complete
        page.wait_for_load_state("networkidle")

        print("✅ Current page:", page.url)

        # You can extract or return this URL to feed into your filling agent
        final_url = page.url

        #browser.close()
        return final_url

if __name__ == "__main__":
    url = navigate_to_epay_tax()
    print("Final URL:", url)
