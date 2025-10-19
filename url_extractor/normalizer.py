import re
from typing import Dict

WHITESPACE_RE = re.compile(r"\s+")


def normalize_user_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = text.lower()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def extract_keywords(text: str) -> Dict[str, bool]:
    """Very small heuristic keyword extractor to aid resolvers.
    Returns a dict of tokens for quick membership tests.
    """
    tokens = re.findall(r"[a-zA-Z0-9_-]+", text.lower())
    return {t: True for t in tokens}
