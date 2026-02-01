#!/usr/bin/env python3
"""
Quick test for the dynamic URL extractor
"""
import asyncio
import json
import google.generativeai as genai
from config import GEMINI_API_KEY
from dynamic_url_extractor import find_best_url

async def test_extractor():
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    
    with open("forms.json") as f:
        forms = json.load(f)
    
    test_queries = [
        "I want to fill JEE form",
        "help me with NTA JEE application",
        "income tax filing",
        "passport application india",
        "practice login test",
        "student survey form"
    ]
    
    print("=" * 70)
    print("TESTING DYNAMIC URL EXTRACTOR")
    print("=" * 70)
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        print("-" * 70)
        url, form_key, reason = await find_best_url(query, forms, gemini_model)
        print(f"✅ URL: {url}")
        print(f"📋 Form Key: {form_key}")
        print(f"📌 Reason: {reason}")

if __name__ == "__main__":
    asyncio.run(test_extractor())
