from __future__ import annotations
import asyncio
from typing import Dict, Any, Optional, Tuple
from .resolvers import resolve_candidates
from .verify import verify_url


async def resolve_form_url(user_text: str, verify: bool = True, timeout_s: int = 20) -> Tuple[Optional[str], Dict[str, Any]]:
    """High-level API to get the best URL for a user request.
    Returns (url, metadata). metadata contains candidates and verification info.
    """
    candidates = resolve_candidates(user_text)
    meta: Dict[str, Any] = {"candidates": candidates}
    if not candidates:
        return None, meta

    if not verify:
        best = candidates[0]
        meta["selected"] = best
        return best.get("url"), meta

    # Verify in order until one passes
    for cand in candidates[:5]:
        ok, reason = await verify_url(cand["url"], timeout_ms=timeout_s * 1000)
        cand["verify"] = {"ok": ok, "reason": reason}
        if ok:
            meta["selected"] = cand
            return cand["url"], meta
    # none verified, return top anyway
    meta["selected"] = candidates[0]
    return candidates[0]["url"], meta
