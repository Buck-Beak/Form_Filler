from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
from google import genai  # pip install google-genai
import re
import json

# ------------------- CONFIG -------------------
WEBSITE_URL = "https://practicetestautomation.com/practice-test-login/"   # 🔹 Change this to your target site
GEMINI_API_KEY = "AIzaSyBptPcrqhaQ25fkQKb5dT6w3nhALnhnL4k"              # 🔹 Add your Gemini API key here
MODEL = "gemini-2.0-flash"

# Test autofill values
autofill_values = {
    "name": "John Doe",
    "email": "test@example.com",
    "password": "Password123!",
    "phone": "9876543210",
    "address": "123 Main Street"
}
# ------------------------------------------------


def extract_form_fields(driver):
    """Extract form fields with attributes and labels"""
    fields = []

    # Get input + textarea
    inputs = driver.find_elements(By.XPATH, "//input | //textarea")

    for inp in inputs:
        field_id = inp.get_attribute("id")
        field_name = inp.get_attribute("name")
        field_placeholder = inp.get_attribute("placeholder")
        field_type = inp.get_attribute("type")

        # Try to get <label> linked with this input
        label_text = None
        if field_id:
            try:
                label_elem = driver.find_element(By.XPATH, f"//label[@for='{field_id}']")
                label_text = label_elem.text
            except:
                pass

        fields.append({
            "id": field_id,
            "name": field_name,
            "placeholder": field_placeholder,
            "type": field_type,
            "label": label_text
        })

    return fields


def classify_fields_with_gemini(fields):
    """Send extracted fields to Gemini for classification"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    You are given form fields from a webpage. 
    Each field has attributes: id, name, placeholder, type, and label.
    
    Classify each field into one of these categories:
    - name
    - email
    - password
    - phone
    - address
    - other

    Return JSON ONLY, no explanations, no markdown fences:
    [
      {{"id": "...", "category": "..."}},
      ...
    ]

    Fields:
    {fields}
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    raw_text = response.text.strip()

    # 🔹 Remove ```json ... ``` wrappers if present
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)

    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini output parse error:", raw_text, e)
        return []


def autofill_form(driver, classified_fields):
    """Fill the form fields with test data"""
    for mapping in classified_fields:
        field_id = mapping.get("id")
        category = mapping.get("category")

        value = autofill_values.get(category)
        if not value or not field_id:
            continue

        try:
            elem = driver.find_element(By.ID, field_id)
            elem.clear()
            elem.send_keys(value)
        except Exception as e:
            print(f"Could not fill {field_id}: {e}")


if __name__ == "__main__":
    # Start Selenium (Chrome)
    driver = webdriver.Chrome()
    driver.get(WEBSITE_URL)
    time.sleep(3)  # wait for page to load

    # Step 1: Extract form fields
    fields = extract_form_fields(driver)
    print("Extracted fields:", fields)

    # Step 2: Classify with Gemini
    classified = classify_fields_with_gemini(fields)
    print("Gemini classified fields:", classified)

    # Step 3: Autofill
    autofill_form(driver, classified)

    # Keep browser open for review
    time.sleep(10)
    driver.quit()
