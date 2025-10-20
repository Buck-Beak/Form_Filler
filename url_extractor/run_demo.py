import asyncio
import json
import sys
from .service import resolve_form_url

async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m url_extractor.run_demo \"<your request>\" [--visible]")
        print("\nExamples:")
        print('  python -m url_extractor.run_demo "I want to pay my income tax"')
        print('  python -m url_extractor.run_demo "help me e-verify my ITR" --visible')
        print("\nOptions:")
        print("  --visible: Run browser in visible mode (for manual login if needed)")
        return
    
    query = sys.argv[1]
    headless = "--visible" not in sys.argv
    
    print(f"\n{'='*60}")
    print(f"🔍 Resolving form URL for: {query}")
    print(f"🖥️  Mode: {'Headless' if headless else 'Visible (for login)'}")
    print(f"{'='*60}\n")
    
    url, meta = await resolve_form_url(
        query, 
        verify=True, 
        navigate=True,
        headless=headless,
        timeout_s=20
    )
    
    print(f"\n{'='*60}")
    print("📊 RESULTS:")
    print(f"{'='*60}")
    print(f"✅ Best URL: {url}")
    
    if meta.get("needs_login"):
        print("⚠️  Login Required: Try running with --visible flag")
    
    if meta.get("navigation"):
        nav = meta["navigation"]
        print(f"\n🧭 Navigation:")
        print(f"   Found: {nav.get('found')}")
        print(f"   Final URL: {nav.get('final_url')}")
        print(f"   Reason: {nav.get('reason')}")
        if nav.get("steps"):
            print(f"   Steps: {', '.join(nav['steps'])}")
    
    print(f"\n📋 All Candidates ({len(meta.get('candidates', []))}):")
    for i, cand in enumerate(meta.get("candidates", [])[:5], 1):
        print(f"   {i}. [{cand.get('score', 0):.2f}] {cand.get('title')}")
        print(f"      {cand.get('url')}")
        if cand.get("navigation"):
            nav = cand["navigation"]
            status = "✅ Found" if nav.get("found") else f"❌ {nav.get('reason')}"
            print(f"      Navigation: {status}")
    
    print(f"\n💾 Full metadata:")
    print(json.dumps(meta, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())
