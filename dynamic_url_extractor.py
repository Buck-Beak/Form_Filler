"""
Dynamic URL extractor using AI to understand user intent and find the best matching form URL.
Uses web search (DuckDuckGo) to find real URLs.
"""
import asyncio
import json
import re
from typing import Optional, Tuple, List
import google.generativeai as genai

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


class DynamicURLExtractor:
    """Uses Gemini to understand user intent and web search to find URLs."""

    def __init__(self, gemini_model: genai.GenerativeModel, forms_db: dict, official_urls: dict = None):
        self.model = gemini_model
        self.forms_db = forms_db
        self.official_urls = official_urls or {}

    async def extract_url_from_intent(self, user_intent: str) -> Tuple[Optional[str], str, str]:
        """
        Extract URL from user intent using AI understanding and web search.
        
        Returns: (url, form_key, reason)
        """
        # First, check official URLs database
        matched_url, matched_key, reason = self._match_official_url(user_intent)
        if matched_url:
            return matched_url, matched_key, reason
        
        # Then try to match against known forms (high confidence)
        matched_url, matched_key = self._match_known_form(user_intent)
        if matched_url:
            confidence = self._calculate_match_confidence(user_intent, matched_key)
            if confidence > 0.7:
                return matched_url, matched_key, f"High-confidence match: {matched_key}"

        # If no strong match, search the web
        print(f"[DynamicExtractor] No strong match in database, searching web...")
        url, form_key, reason = await self._web_search(user_intent)
        if url:
            return url, form_key, reason
        
        # Fallback: use Gemini to pick from database with lower confidence
        print(f"[DynamicExtractor] Web search failed, falling back to database...")
        url, form_key, reason = await self._gemini_fallback_search(user_intent)
        return url, form_key, reason

    def _match_official_url(self, user_intent: str) -> Tuple[Optional[str], str, str]:
        """Check if intent matches any official government URLs."""
        intent_lower = user_intent.lower()
        
        for form_key, form_info in self.official_urls.items():
            keywords = form_info.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in intent_lower:
                    return form_info["url"], form_key, f"Found official form: {form_info['description']}"
        
        return None, "", ""

    def _calculate_match_confidence(self, user_intent: str, form_key: str) -> float:
        """Calculate how well the form key matches the intent."""
        intent_lower = user_intent.lower()
        form_key_lower = form_key.lower()
        
        # Exact match
        if form_key_lower in intent_lower:
            return 0.95
        
        # Partial match
        form_words = form_key_lower.split("_")
        matched_words = sum(1 for word in form_words if word in intent_lower)
        confidence = matched_words / len(form_words) if form_words else 0
        return confidence

    def _match_known_form(self, user_intent: str) -> Tuple[Optional[str], str]:
        """Try to match user intent against known forms in database."""
        intent_lower = user_intent.lower()
        
        best_match = None
        best_score = 0
        
        for form_key, form_info in self.forms_db.items():
            # Check direct keyword match
            if form_key.lower() in intent_lower:
                return form_info["url"], form_key
            
            # Score based on word matches
            form_key_words = form_key.lower().split("_")
            matched = sum(1 for word in form_key_words if word in intent_lower and len(word) > 2)
            score = matched / len(form_key_words) if form_key_words else 0
            
            if score > best_score:
                best_score = score
                best_match = (form_info["url"], form_key)
        
        if best_score > 0.7:
            return best_match
        
        return None, ""

    async def _web_search(self, user_intent: str) -> Tuple[Optional[str], str, str]:
        """Search the web for a form matching the user intent."""
        if not requests or not BeautifulSoup:
            print("[WebSearch] Web search libraries not available, using direct URLs")
            return self._search_using_known_urls(user_intent)
        
        # Build search query
        search_query = self._build_search_query(user_intent)
        print(f"[WebSearch] Searching for: {search_query}")
        
        try:
            # Try multiple search approaches
            urls = await self._try_duckduckgo(search_query)
            if not urls:
                urls = await self._try_google_cache(search_query)
            
            if not urls:
                print("[WebSearch] No URLs found, trying known URL patterns")
                return self._search_using_known_urls(user_intent)
            
            # Use Gemini to pick the best result
            best_url, best_title, reason = await self._pick_best_url(user_intent, urls)
            if best_url:
                form_key = self._extract_form_key(best_title)
                return best_url, form_key, f"Found via web search: {reason}"
            
            return None, "", "Could not identify best URL from search results"
            
        except Exception as e:
            print(f"[WebSearch] Error: {e}")
            return self._search_using_known_urls(user_intent)

    async def _try_duckduckgo(self, search_query: str) -> List[Tuple[str, str]]:
        """Try to search using DuckDuckGo."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": search_query},
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            urls = []
            
            for result in soup.select("a.result__a"):
                href = result.get("href")
                if href and href.startswith("http"):
                    title = result.get_text().strip()
                    urls.append((href, title))
                    if len(urls) >= 5:
                        break
            
            return urls
        except Exception as e:
            print(f"[DuckDuckGo] Search failed: {e}")
            return []

    async def _try_google_cache(self, search_query: str) -> List[Tuple[str, str]]:
        """Try Google cache as fallback."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # Use Google with site restrictions
            response = requests.get(
                "https://www.google.com/search",
                params={"q": search_query, "filter": "0"},
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            # Extract URLs from Google results
            soup = BeautifulSoup(response.text, "html.parser")
            urls = []
            
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.startswith("http") and "google" not in href:
                    title = link.get_text().strip()
                    if title and len(title) > 3:
                        urls.append((href, title))
                        if len(urls) >= 5:
                            break
            
            return urls
        except Exception as e:
            print(f"[Google] Search failed: {e}")
            return []

    def _search_using_known_urls(self, user_intent: str) -> Tuple[Optional[str], str, str]:
        """Fallback: intelligently suggest URL based on intent keywords."""
        intent_lower = user_intent.lower()
        keywords_map = {
            "jee": "JEE Main/Advanced form (not in database, visit nta.ac.in)",
            "neet": "NEET form (not in database, visit neet.nta.ac.in)",
            "passport": "passport_seva",
            "tax": "epaytax",
            "income": "epaytax",
            "verify": "everify",
        }
        
        for keyword, suggestion in keywords_map.items():
            if keyword in intent_lower:
                if suggestion in self.forms_db:
                    return self.forms_db[suggestion]["url"], suggestion, f"Matched keyword: {keyword}"
                else:
                    return None, suggestion, f"Form '{suggestion}' not in database. Please visit the official website."
        
        return None, "", "Could not find matching URL"

    async def _pick_best_url(self, user_intent: str, urls: List[Tuple[str, str]]) -> Tuple[Optional[str], str, str]:
        """Use Gemini to pick the best URL from search results."""
        url_list = "\n".join([f"- {title}: {url}" for url, title in urls])
        
        prompt = (
            f"The user wants to: {user_intent}\n\n"
            f"Top search results:\n{url_list}\n\n"
            "Which URL is MOST relevant for this intent? Return ONLY a JSON response:\n"
            "{\n"
            '  "url": "the_best_url",\n'
            '  "title": "the_page_title",\n'
            '  "reason": "why_this_is_the_best_match"\n'
            "}"
        )
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("url"), result.get("title", ""), result.get("reason", "")
        except Exception as e:
            print(f"[Gemini] URL picking failed: {e}")
        
        # Fallback: return first URL
        return urls[0][0], urls[0][1], "Fallback: first search result"

    def _build_search_query(self, user_intent: str) -> str:
        """Build an optimized search query."""
        # Extract key terms
        terms = user_intent.lower().replace("fill", "").replace("form", "").strip()
        return f"{terms} form official site:gov.in OR site:nic.in"

    def _extract_form_key(self, title: str) -> str:
        """Extract a form key from the title."""
        # Clean up title and create a key
        key = re.sub(r'[^a-zA-Z0-9]', '_', title[:30].lower())
        return key.strip("_") or "web_form"

    async def _gemini_fallback_search(self, user_intent: str) -> Tuple[Optional[str], str, str]:
        """Fallback: use Gemini to pick from database forms."""
        forms_list = "\n".join([
            f"- {key}: {info['url']}"
            for key, info in self.forms_db.items()
        ])

        prompt = (
            "You are a form-filling assistant. The user wants to fill a form but your web search didn't find it.\n"
            f"User Intent: {user_intent}\n\n"
            f"Available forms in database:\n{forms_list}\n\n"
            "Pick the CLOSEST match even if not perfect. Return ONLY JSON:\n"
            "{\n"
            '  "form_key": "key",\n'
            '  "url": "url",\n'
            '  "confidence": 0.5,\n'
            '  "reason": "why_this_is_closest"\n'
            "}"
        )

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                if result.get("confidence", 0) > 0.3:
                    return result.get("url"), result.get("form_key", ""), result.get("reason", "")
        except Exception as e:
            print(f"[Gemini] Fallback search failed: {e}")

        return None, "", "Could not find matching form"


async def find_best_url(user_intent: str, forms_db: dict, gemini_model: genai.GenerativeModel, official_urls: dict = None) -> Tuple[Optional[str], str, str]:
    """
    Convenience function to extract best URL for user intent.
    
    Returns: (url, form_key, reason)
    """
    if official_urls is None:
        official_urls = {}
    extractor = DynamicURLExtractor(gemini_model, forms_db, official_urls)
    return await extractor.extract_url_from_intent(user_intent)
