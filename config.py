import os
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Local Electron app (standalone_app) HTTP API — must match electron/main.js port
STANDALONE_APP_BASE = os.environ.get("STANDALONE_APP_BASE", "http://127.0.0.1:5000").rstrip("/")
