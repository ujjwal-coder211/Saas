"""Browser tools for Sarva Agent (Harness) — Chrome DevTools Protocol via Playwright.

Implements the paper's §4.2.2 browser tool taxonomy: open, click, type, extract,
screenshot, wait, navigate, execute. A single Chromium session is kept alive in a
dedicated worker thread so cookies/auth state persist across calls (paper: "navigate
in existing session, preserves cookies and auth state").

Playwright is an OPTIONAL dependency. When it is not installed, every tool returns a
clean ``ok: False`` with an install hint instead of raising — matching the graceful
degradation pattern used by the rest of the Harness.

    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import base64
import os
import queue
import threading
from typing import Any

# Headless by default (servers have no display); set BROWSER_HEADED=1 for local debugging.
_HEADED = os.environ.get("BROWSER_HEADED", "").lower() in ("1", "true", "yes")
_NAV_TIMEOUT_MS = int(os.environ.get("BROWSER_TIMEOUT_MS", "20000"))
_SCREENSHOT_MAX_B64 = 4_000_000  # ~3MB raw image cap before base64


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except Exception:
        return False


class _BrowserWorker:
    """Runs Playwright's sync API in its own thread.

    The Harness ``run_tool`` dispatcher is synchronous but is called from inside the
    server's asyncio loop. Playwright's sync API refuses to run on a thread that owns a
    running event loop, so all browser work is funneled to this dedicated worker thread
    (which has no loop). Commands go in via a queue; results come back per-command.
    """

    def __init__(self) -> None:
        self._cmds: queue.Queue[tuple[str, dict, queue.Queue]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started = False

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._started:
                return
            self._thread = threading.Thread(target=self._run, name="aksh-browser", daemon=True)
            self._thread.start()
            self._started = True

    def submit(self, action: str, args: dict, *, timeout: float = 60.0) -> dict[str, Any]:
        if not _playwright_available():
            return {
                "ok": False,
                "error": "Browser tools need Playwright. Run: pip install playwright "
                "&& playwright install chromium",
            }
        self._ensure_thread()
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._cmds.put((action, args, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": f"Browser action '{action}' timed out"}

    # --- worker thread internals -------------------------------------------------
    def _run(self) -> None:
        from playwright.sync_api import sync_playwright

        page = None
        browser = None
        with sync_playwright() as pw:
            while True:
                action, args, reply = self._cmds.get()
                try:
                    if action == "_shutdown":
                        reply.put({"ok": True})
                        break

                    if browser is None:
                        browser = pw.chromium.launch(headless=not _HEADED)
                        page = browser.new_page()
                        page.set_default_timeout(_NAV_TIMEOUT_MS)

                    reply.put(self._dispatch(page, action, args))
                except Exception as exc:  # never let the worker die on one bad call
                    reply.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _dispatch(page, action: str, args: dict) -> dict[str, Any]:
        if action in ("open", "navigate"):
            url = args.get("url", "")
            if not url:
                return {"ok": False, "error": "url required"}
            page.goto(url, wait_until="domcontentloaded")
            return {"ok": True, "url": page.url, "title": page.title()}

        if action == "click":
            sel = args.get("selector", "")
            page.click(sel)
            return {"ok": True, "selector": sel}

        if action == "type":
            sel = args.get("selector", "")
            page.fill(sel, args.get("text", ""))
            return {"ok": True, "selector": sel}

        if action == "extract":
            sel = args.get("selector", "")
            els = page.query_selector_all(sel)
            items = [(e.inner_text() or "").strip() for e in els]
            return {"ok": True, "selector": sel, "count": len(items), "items": items[:100]}

        if action == "screenshot":
            raw = page.screenshot(full_page=bool(args.get("full_page", True)))
            b64 = base64.b64encode(raw).decode("ascii")
            if len(b64) > _SCREENSHOT_MAX_B64:
                return {"ok": False, "error": "Screenshot too large; narrow the region or scope"}
            return {"ok": True, "format": "png", "base64": b64, "bytes": len(raw)}

        if action == "wait":
            cond = args.get("condition", "networkidle")
            if cond in ("load", "domcontentloaded", "networkidle"):
                page.wait_for_load_state(cond)
            else:  # treat as a selector
                page.wait_for_selector(cond)
            return {"ok": True, "condition": cond}

        if action == "execute":
            value = page.evaluate(args.get("js", ""))
            return {"ok": True, "result": value}

        return {"ok": False, "error": f"Unknown browser action: {action}"}


_WORKER = _BrowserWorker()


def browser_open(url: str) -> dict[str, Any]:
    """Launch Chromium, navigate to ``url``, wait for DOM ready."""
    return _WORKER.submit("open", {"url": url})


def browser_navigate(url: str) -> dict[str, Any]:
    """Navigate in the existing session (preserves cookies + auth state)."""
    return _WORKER.submit("navigate", {"url": url})


def browser_click(selector: str) -> dict[str, Any]:
    return _WORKER.submit("click", {"selector": selector})


def browser_type(selector: str, text: str) -> dict[str, Any]:
    return _WORKER.submit("type", {"selector": selector, "text": text})


def browser_extract(selector: str) -> dict[str, Any]:
    return _WORKER.submit("extract", {"selector": selector})


def browser_screenshot(full_page: bool = True) -> dict[str, Any]:
    return _WORKER.submit("screenshot", {"full_page": full_page})


def browser_wait(condition: str = "networkidle") -> dict[str, Any]:
    return _WORKER.submit("wait", {"condition": condition})


def browser_execute(js: str) -> dict[str, Any]:
    return _WORKER.submit("execute", {"js": js})
