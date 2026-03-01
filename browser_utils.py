from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async, StealthConfig
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False
    print("[STEALTH] playwright-stealth not installed — run: pip install playwright-stealth")


async def launch_browser():
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=False,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-notifications',
            '--disable-popup-blocking',
        ]
    )
    browser_context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='Asia/Kolkata',
        permissions=['geolocation'],
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
    )
    page = await browser_context.new_page()

    # ── Layer 1: playwright-stealth (17-vector JS fingerprint patches) ──────────
    if _STEALTH_AVAILABLE:
        await stealth_async(
            page,
            StealthConfig(
                navigator_hardware_concurrency=8,
                vendor='Intel Inc.',
                renderer='Intel Iris OpenGL Engine',
                nav_vendor='Google Inc.',
                languages=('en-US', 'en'),
                navigator_platform=True,
                navigator_plugins=True,
                navigator_user_agent=True,
                webgl_vendor=True,
                chrome_app=True,
                chrome_csi=True,
                chrome_load_times=True,
                chrome_runtime=True,
                iframe_content_window=True,
                media_codecs=True,
                outerdimensions=True,
                hairline=True,
            ),
        )

    # ── Layer 2: Additional custom init script (on top of stealth) ──────────────
    await page.add_init_script("""
        // Belt-and-suspenders: ensure webdriver is hidden even if stealth was skipped
        try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch(e) {}
        // Chrome object
        window.chrome = window.chrome || { runtime: {}, app: {}, csi: function(){}, loadTimes: function(){} };
        // Plugins count
        if (!navigator.plugins || navigator.plugins.length === 0) {
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
                configurable: true
            });
        }
        // Platform
        try { Object.defineProperty(navigator, 'platform', { get: () => 'Win32' }); } catch(e) {}
        // Languages
        try { Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] }); } catch(e) {}
        // Notification permission (non-automation default)
        const origQuery = window.navigator.permissions && window.navigator.permissions.query;
        if (origQuery) {
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(parameters);
        }
    """)

    return p, browser, browser_context, page
