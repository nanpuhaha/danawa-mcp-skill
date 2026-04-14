"""Playwright-based browser with human-like behaviour and JSON network capture.

The :class:`DanawaBrowser` wraps an async Playwright browser context and adds:

* **Human-like delays** — random sleeps between actions to avoid bot detection.
* **Network capture** — every JSON response emitted while a page is open is
  collected so callers can use the clean API data directly instead of parsing
  HTML.

Usage (as an async context manager)::

    async with DanawaBrowser() as browser:
        html, captured = await browser.navigate("https://prod.danawa.com/...")

Or via the module-level singleton::

    browser = await get_browser()
    html, captured = await browser.navigate(url)
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger
from playwright.async_api import (
    BrowserContext,
    Page,
    Response,
    async_playwright,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DANAWA_BASE_URL = "https://www.danawa.com"
DANAWA_PROD_URL = "https://prod.danawa.com"
DANAWA_SEARCH_URL = "https://search.danawa.com"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# JSON content-type fragment
_JSON_CT = "json"


# ---------------------------------------------------------------------------
# Network capture helper
# ---------------------------------------------------------------------------


class NetworkCapture:
    """Accumulates JSON API responses from a Playwright page.

    Attach via ``page.on("response", capture.handle_response)`` before any
    navigation to ensure all responses are captured.
    """

    def __init__(self) -> None:
        self._responses: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def handle_response(self, response: Response) -> None:
        """Playwright response callback — called for every network response."""
        content_type = response.headers.get("content-type", "")
        if _JSON_CT not in content_type:
            return
        if not response.ok:
            return
        try:
            body = await response.json()
            async with self._lock:
                self._responses.append(
                    {
                        "url": response.url,
                        "status": response.status,
                        "data": body,
                    }
                )
        except Exception:
            # Body may not be valid JSON even with json content-type
            pass

    def get(self) -> list[dict[str, Any]]:
        """Return a snapshot of all captured responses so far."""
        return list(self._responses)

    def clear(self) -> None:
        """Discard all captured responses."""
        self._responses.clear()


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------


class DanawaBrowser:
    """Async Playwright browser context pre-configured for Danawa.

    Use as an async context manager or call :meth:`start` / :meth:`stop`
    explicitly.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the Playwright browser and create the browser context."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            # Suppress the "webdriver" navigator flag
            java_script_enabled=True,
        )
        # Conceal automation indicators
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        logger.info("DanawaBrowser started")

    async def stop(self) -> None:
        """Close the browser and Playwright instance."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("DanawaBrowser stopped")

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> DanawaBrowser:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------

    def _require_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._context

    async def new_page(self) -> tuple[Page, NetworkCapture]:
        """Open a new page with network capture enabled."""
        ctx = self._require_context()
        capture = NetworkCapture()
        page = await ctx.new_page()
        page.on("response", capture.handle_response)
        return page, capture

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    async def navigate(
        self,
        url: str,
        *,
        wait_until: str = "networkidle",
        timeout: int = 30_000,
        close_page: bool = True,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Navigate to *url* and return ``(html_content, captured_json_list)``.

        Parameters
        ----------
        url:
            The URL to navigate to.
        wait_until:
            Playwright ``wait_until`` strategy (default ``"networkidle"``).
        timeout:
            Navigation timeout in milliseconds.
        close_page:
            Whether to close the page after navigation (default ``True``).
        """
        page, capture = await self.new_page()
        try:
            await _human_delay(0.2, 0.8)
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            await _human_delay(0.5, 1.5)
            html = await page.content()
            return html, capture.get()
        finally:
            if close_page:
                await page.close()

    async def navigate_and_interact(
        self,
        url: str,
        *,
        wait_until: str = "networkidle",
        timeout: int = 30_000,
    ) -> tuple[Page, NetworkCapture]:
        """Navigate to *url* and return the *open* page for further interaction.

        The caller is responsible for closing the page when done::

            page, capture = await browser.navigate_and_interact(url)
            try:
                # interact with page ...
            finally:
                await page.close()
        """
        page, capture = await self.new_page()
        await _human_delay(0.2, 0.8)
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        await _human_delay(0.5, 1.5)
        return page, capture

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout: int = 15_000,
    ) -> Any:
        """Make a lightweight JSON POST request via ``fetch`` in the browser context.

        This reuses the existing browser cookies/session and bypasses stricter
        CORS checks that might block plain ``httpx`` requests.
        """
        ctx = self._require_context()
        page = await ctx.new_page()
        try:
            result = await page.evaluate(
                """
                async ([url, payload]) => {
                    const res = await fetch(url, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload),
                    });
                    return await res.json();
                }
                """,
                [url, payload],
            )
            return result
        finally:
            await page.close()

    async def fetch_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int = 15_000,
    ) -> Any:
        """Make a lightweight GET request and return parsed JSON.

        Runs inside the existing browser context so cookies are included.
        """
        ctx = self._require_context()
        page = await ctx.new_page()
        try:
            if params:
                from urllib.parse import urlencode

                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urlencode(params)}"

            result = await page.evaluate(
                """
                async (url) => {
                    const res = await fetch(url);
                    return await res.json();
                }
                """,
                url,
            )
            return result
        finally:
            await page.close()


# ---------------------------------------------------------------------------
# Human-like delays
# ---------------------------------------------------------------------------


async def _human_delay(min_sec: float = 0.3, max_sec: float = 1.2) -> None:
    """Random sleep to simulate human interaction speed."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


# ---------------------------------------------------------------------------
# Module-level singleton with lazy initialisation
# ---------------------------------------------------------------------------

_browser: DanawaBrowser | None = None
_browser_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Return (or lazily create) the browser initialisation lock.

    The lock is created lazily because ``asyncio.Lock()`` must be created
    inside a running event loop.
    """
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    return _browser_lock


async def get_browser() -> DanawaBrowser:
    """Return the shared :class:`DanawaBrowser` singleton.

    Initialises (starts) the browser on first call.
    """
    global _browser
    async with _get_lock():
        if _browser is None:
            _browser = DanawaBrowser()
            await _browser.start()
    return _browser


async def close_browser() -> None:
    """Stop and discard the shared browser singleton."""
    global _browser
    async with _get_lock():
        if _browser is not None:
            await _browser.stop()
            _browser = None


@asynccontextmanager
async def browser_session() -> AsyncGenerator[DanawaBrowser, None]:
    """Async context manager that provides a fresh :class:`DanawaBrowser`.

    Suitable for one-off scripts or tests that need an isolated browser.
    For the MCP server use :func:`get_browser` instead.
    """
    async with DanawaBrowser() as browser:
        yield browser
