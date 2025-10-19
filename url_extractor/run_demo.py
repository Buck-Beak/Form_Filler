import asyncio
import json
import sys
from .service import resolve_form_url

async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m url_extractor.run_demo \"<your request>\"")
        return
    query = sys.argv[1]
    url, meta = await resolve_form_url(query, verify=True, timeout_s=20)
    print("Best URL:", url)
    print("Details:\n", json.dumps(meta, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
