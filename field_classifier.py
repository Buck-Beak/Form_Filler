import json
import re
import google.generativeai as genai

def classify_fields_with_gemini(fields, gemini_model):
    prompt = f"""
You are given form fields from a webpage. 
Each field has attributes: id, name, placeholder, type, and label.
Classify each field into one of these categories:
- name
- email
- password
- phone
- address
- father_name
- mother_name
- aadhaar_number
- date_of_birth
- assessment_year
- pan
- dob
- mobile
- other
Return JSON ONLY (no markdown, no explanation), format:
[
  {{"id": "...", "name": "...", "category": "..."}},
  ...
]
Fields:
{json.dumps(fields, indent=2)}
"""
    response = gemini_model.generate_content(prompt)
    raw_text = response.text.strip()
    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
    raw_text = re.sub(r"```$", "", raw_text)
    try:
        return json.loads(raw_text)
    except Exception as e:
        print("Gemini parse error:", raw_text, e)
        return []
