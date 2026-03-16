import json
import re
import time
import asyncio
import os
import tempfile
import requests
import aiohttp  # async HTTP client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import google.generativeai as genai
from config import GEMINI_API_KEY, TELEGRAM_TOKEN

SERP_API_KEY = "e60f53053aa43c29c26088b2663663407e4409459246ad4a1af5efacfe1cd186"

async def generate_search_query(user_prompt: str, gemini_model):
    prompt = (
        "Convert the user request into a Google search query "
        "to find the official indian government or organization form website.\n"
        "Return ONLY plain text.\n\n"
        f"User request: {user_prompt}"
    )

    response = gemini_model.generate_content(prompt)
    return response.text.strip()


def search_form_url(query: str):
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "num": 5
    }

    res = requests.get("https://serpapi.com/search", params=params)
    data = res.json()

    for result in data.get("organic_results", []):
        link = result.get("link", "")

        # Optional domain filter
        if any(d in link for d in ["gov.in", "nic.in", "org"]):
            return link, result.get("title")

    # fallback: first result
    if data.get("organic_results"):
        r = data["organic_results"][0]
        return r.get("link"), r.get("title")

    return None, None

async def generate_form_url(user_prompt: str, gemini_model):
    query = await generate_search_query(user_prompt, gemini_model)
    print("🔍 Search Query:", query)

    url, title = search_form_url(query)
    return url, title

