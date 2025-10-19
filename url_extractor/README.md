# URL Extractor (AI-driven)

This module resolves the correct form URL from a free-text user request using a pipeline:
- Known forms lookup (uses project-level `forms.json`)
- Synonym matching
- AI intent resolution (Google Gemini)
- Web search fallback (DuckDuckGo HTML)
- Optional stealth verification using Playwright to overcome anti-bot checks

## Files
- `config.py` — loads `.env` (GEMINI_API_KEY optional), sets default user-agent
- `normalizer.py` — text normalization and keyword extraction
- `resolvers.py` — implements the resolver pipeline and returns candidates with scores
- `verify.py` — opens pages via Playwright with anti-detection and verifies accessibility
- `service.py` — high-level API `resolve_form_url()` combining resolvers and verification
- `run_demo.py` — CLI to try the resolver locally

## Setup
1. Ensure you have the project `.env` with optional `GEMINI_API_KEY`.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

The top-level `requirements.txt` already contains `playwright` and `google-generativeai`. If `bs4` and `requests` are missing, add/install them:

```powershell
pip install beautifulsoup4 requests
```

Install Playwright browsers if not already done:

```powershell
python -m playwright install chromium
```

## Try it

```powershell
python -m url_extractor.run_demo "I want to pay my income tax online"
python -m url_extractor.run_demo "help me e-verify my ITR"
python -m url_extractor.run_demo "jee main application form"
```

`resolve_form_url()` returns the best URL and a metadata dict containing examined candidates and verification results.

## Integrating later with the bot
Keep `main.py` unchanged. Later, you can replace `get_form_url()` with a call to this module and map the returned URL back into your flow.
