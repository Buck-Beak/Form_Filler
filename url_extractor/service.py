from __future__ import annotations
import asyncio
from typing import Dict, Any, Optional, Tuple
from .resolvers import resolve_candidates
from .verify import verify_url, verify_and_navigate_to_form


async def resolve_form_url(
    user_text: str, 
    verify: bool = True, 
    navigate: bool = True,
    headless: bool = True,
    timeout_s: int = 20
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    High-level API to get the best URL for a user request.
    
    Args:
        user_text: User's form request
        verify: Whether to verify URLs with Playwright
        navigate: If True, intelligently navigate to find form page
        headless: Browser visibility (False = visible for manual login)
        timeout_s: Timeout per URL check
    
    Returns:
        (url, metadata) where metadata contains:
        - candidates: list of candidate URLs with scores
        - selected: the chosen candidate
        - navigation: navigation details if navigate=True
        - needs_login: whether manual login is required
    """
    candidates = resolve_candidates(user_text)
    meta: Dict[str, Any] = {"candidates": candidates, "needs_login": False}
    
    if not candidates:
        return None, meta

    if not verify:
        best = candidates[0]
        meta["selected"] = best
        return best.get("url"), meta

    # Try candidates with navigation if enabled
    if navigate:
        for cand in candidates[:5]:
            print(f"\n🔍 Trying candidate: {cand['url']} (score: {cand['score']:.2f})")
            nav_result = await verify_and_navigate_to_form(
                cand["url"], 
                user_text, 
                headless=headless,
                timeout_ms=timeout_s * 1000
            )
            cand["navigation"] = nav_result
            
            if nav_result["found"]:
                print(f"✅ Found form at: {nav_result['final_url']}")
                meta["selected"] = cand
                meta["navigation"] = nav_result
                return nav_result["final_url"], meta
            else:
                print(f"❌ {nav_result['reason']}")
                if nav_result["needs_login"]:
                    meta["needs_login"] = True
                    if not headless:
                        # User had chance to login, but didn't succeed
                        print("⚠️ Login was required but not completed successfully")
        
        # None found with navigation
        print("❌ Could not find form page in any candidate")
        meta["selected"] = candidates[0]
        meta["navigation"] = candidates[0].get("navigation", {})
        return candidates[0]["url"], meta
    
    else:
        # Simple verification without navigation
        for cand in candidates[:5]:
            ok, reason = await verify_url(cand["url"], timeout_ms=timeout_s * 1000)
            cand["verify"] = {"ok": ok, "reason": reason}
            if ok:
                meta["selected"] = cand
                return cand["url"], meta
        
        # None verified, return top anyway
        meta["selected"] = candidates[0]
        return candidates[0]["url"], meta
