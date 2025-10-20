from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    import google.generativeai as genai
except Exception:
    genai = None  # optional

from .config import GEMINI_API_KEY, SERPAPI_API_KEY, DEFAULT_USER_AGENT
from .normalizer import normalize_user_text, extract_keywords

ROOT = Path(__file__).resolve().parents[1]
FORMS_JSON = ROOT / "forms.json"


def load_forms_db() -> Dict[str, Dict[str, Any]]:
    if FORMS_JSON.exists():
        with open(FORMS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def canonicalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


class ResolutionCandidate(Dict[str, Any]):
    # keys: url, title, score, source, debug
    pass


class KnownFormsResolver:
    def __init__(self, forms_db: Dict[str, Dict[str, Any]]):
        self.forms_db = forms_db
        self.index = {canonicalize_key(k): v for k, v in forms_db.items()}

    def resolve(self, user_text: str) -> List[ResolutionCandidate]:
        nt = normalize_user_text(user_text)
        tokens = extract_keywords(nt)
        cands: List[ResolutionCandidate] = []
        # direct key match
        for k, entry in self.index.items():
            parts = set(k.split("_"))
            overlap = len([p for p in parts if p in tokens])
            if overlap:
                url = entry.get("url")
                if url:
                    cands.append({
                        "url": url,
                        "title": f"Known form: {k}",
                        "score": 0.6 + 0.05 * min(overlap, 4),
                        "source": "known_forms",
                        "debug": {"matched_key": k, "overlap": overlap}
                    })
        return sorted(cands, key=lambda x: x["score"], reverse=True)


SYNONYMS = {
    "epaytax": ["e pay tax", "pay tax", "income tax e-pay", "eportal tax", "epay tax"],
    "everify": ["e verify", "everify", "verify return", "e-verify return", "itr verify"],
    "jee": ["jee main", "nta jee", "jee form"],
}


class SynonymResolver:
    def __init__(self, forms_db: Dict[str, Dict[str, Any]]):
        self.forms_db = forms_db

    def resolve(self, user_text: str) -> List[ResolutionCandidate]:
        nt = normalize_user_text(user_text)
        cands: List[ResolutionCandidate] = []
        for canonical, words in SYNONYMS.items():
            for w in words:
                if w in nt:
                    entry = self.forms_db.get(canonical) or self.forms_db.get(canonicalize_key(canonical))
                    if entry and entry.get("url"):
                        cands.append({
                            "url": entry["url"],
                            "title": f"Synonym match: {w}",
                            "score": 0.7,
                            "source": "synonym",
                            "debug": {"synonym": w}
                        })
                        break
        return sorted({c["url"]: c for c in cands}.values(), key=lambda x: x["score"], reverse=True)


class AIIntentResolver:
    def __init__(self):
        self.enabled = bool(GEMINI_API_KEY and genai)
        if self.enabled:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self.model = None

    def resolve(self, user_text: str, forms_db: Dict[str, Dict[str, Any]]) -> List[ResolutionCandidate]:
        if not self.enabled or not self.model:
            return []
        prompt = f"""
You are a smart URL resolver for government and institutional forms in India.
Given a user request, identify the most likely form and propose up to 3 official URLs to start the process.
Prefer official government domains when applicable. Respond strictly as JSON list of objects with fields:
[{{"title":"...","url":"...","score":0.0,"reason":"..."}}, ...]
User request: {user_text}
Known forms keys (for preference if relevant): {list(forms_db.keys())}
"""
        try:
            resp = self.model.generate_content(prompt)
            text = (resp.text or "").strip()
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"```$", "", text)
            data = json.loads(text)
            cands: List[ResolutionCandidate] = []
            for item in data[:5]:
                url = item.get("url")
                title = item.get("title") or "AI candidate"
                score = float(item.get("score", 0.65))
                cands.append({
                    "url": url,
                    "title": title,
                    "score": max(0.0, min(score, 0.95)),
                    "source": "ai_intent",
                    "debug": {"reason": item.get("reason")}
                })
            # De-dup by URL
            uniq = {}
            for c in cands:
                if c.get("url"):
                    uniq.setdefault(c["url"], c)
            return sorted(uniq.values(), key=lambda x: x["score"], reverse=True)
        except Exception as e:
            # Fallback silently
            return []


class WebSearchResolver:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    def _ddg_search(self, query: str, max_results: int = 5) -> List[Tuple[str, str]]:
        url = "https://duckduckgo.com/html/"
        params = {"q": query}
        r = self.session.get(url, params=params, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("a.result__a"):
            href = a.get("href")
            title = a.get_text(strip=True)
            if href and href.startswith("http"):
                results.append((href, title))
            if len(results) >= max_results:
                break
        return results

    def resolve(self, user_text: str) -> List[ResolutionCandidate]:
        nt = normalize_user_text(user_text)
        query = nt
        pairs = self._ddg_search(query, max_results=6)
        cands: List[ResolutionCandidate] = []
        for href, title in pairs:
            score = 0.55
            # prefer govt domains slightly
            if re.search(r"\.gov\.in|incometax\.gov\.in|nta\.ac\.in|nic\.in", href):
                score += 0.15
            cands.append({
                "url": href,
                "title": title or "search result",
                "score": min(score, 0.8),
                "source": "web_search",
                "debug": {"engine": "ddg"}
            })
        return cands


def resolve_candidates(user_text: str) -> List[ResolutionCandidate]:
    forms_db = load_forms_db()
    pipeline = [
        KnownFormsResolver(forms_db).resolve,
        SynonymResolver(forms_db).resolve,
    ]
    ai = AIIntentResolver()
    pipeline.append(lambda text: ai.resolve(text, forms_db))
    pipeline.append(WebSearchResolver().resolve)

    seen = set()
    all_cands: List[ResolutionCandidate] = []
    for step in pipeline:
        for c in step(user_text):
            url = c.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            all_cands.append(c)
    return sorted(all_cands, key=lambda x: x["score"], reverse=True)
