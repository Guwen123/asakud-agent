from __future__ import annotations

import atexit
import re
import threading
from typing import Any
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool


_BROWSER_LOCK = threading.RLock()
_RUNTIME: "_PlaywrightRuntime | None" = None

_DEFAULT_TIMEOUT_MS = 15000
_MAX_TEXT_CHARS = 8000
_MAX_ELEMENTS = 20
_MAX_AX_DEPTH = 6
_MAX_AX_NODES = 120


def _normalize_whitespace(text: str) -> str:
    value = (text or "").replace("\r", "\n")
    value = re.sub(r"[ \t\f\v]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _shorten(text: str, limit: int = _MAX_TEXT_CHARS) -> str:
    value = _normalize_whitespace(text)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _normalize_whitespace(value)
    return _normalize_whitespace(str(value))


def _looks_like_url(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://") or "." in text


def _resolve_target(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("url is required")
    if raw.startswith(("http://", "https://")):
        return raw, "url"
    if _looks_like_url(raw):
        return f"https://{raw.lstrip('/')}", "url"
    return f"https://duckduckgo.com/?q={quote_plus(raw)}", "search"


class _PlaywrightRuntime:
    def __init__(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(_DEFAULT_TIMEOUT_MS)

    @property
    def page(self):  # noqa: ANN201
        return self._page

    def close(self) -> None:
        for resource in (self._page, self._context, self._browser, self._playwright):
            try:
                resource.close()
            except Exception:
                try:
                    resource.stop()
                except Exception:
                    pass


def _get_runtime() -> _PlaywrightRuntime:
    global _RUNTIME
    with _BROWSER_LOCK:
        if _RUNTIME is None:
            _RUNTIME = _PlaywrightRuntime()
        return _RUNTIME


def _close_runtime() -> None:
    global _RUNTIME
    with _BROWSER_LOCK:
        if _RUNTIME is None:
            return
        _RUNTIME.close()
        _RUNTIME = None


atexit.register(_close_runtime)


def _wait_for_page_settle(page) -> None:  # noqa: ANN001, ANN201
    try:
        page.wait_for_load_state("domcontentloaded", timeout=_DEFAULT_TIMEOUT_MS)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


def _trim_accessibility_tree(node: Any, depth: int = 0, budget: list[int] | None = None) -> dict[str, Any] | None:
    if budget is None:
        budget = [_MAX_AX_NODES]
    if budget[0] <= 0 or depth > _MAX_AX_DEPTH or not isinstance(node, dict):
        return None

    role = _coerce_text(node.get("role"))
    name = _coerce_text(node.get("name"))
    value = _coerce_text(node.get("value"))
    description = _coerce_text(node.get("description"))

    children: list[dict[str, Any]] = []
    budget[0] -= 1
    for child in node.get("children", []) or []:
        compact_child = _trim_accessibility_tree(child, depth=depth + 1, budget=budget)
        if compact_child is not None:
            children.append(compact_child)
        if budget[0] <= 0:
            break

    payload: dict[str, Any] = {}
    if role:
        payload["role"] = role
    if name:
        payload["name"] = name
    if value:
        payload["value"] = value
    if description:
        payload["description"] = description
    if children:
        payload["children"] = children

    if not payload:
        return None
    return payload


def _serialize_accessibility_tree(node: Any, lines: list[str] | None = None, depth: int = 0) -> str:
    if lines is None:
        lines = []
    if not isinstance(node, dict):
        return ""

    role = _coerce_text(node.get("role"))
    name = _coerce_text(node.get("name"))
    value = _coerce_text(node.get("value"))
    description = _coerce_text(node.get("description"))

    parts = [part for part in [role, name, value, description] if part]
    if parts:
        prefix = "  " * depth + "- "
        lines.append(prefix + " | ".join(parts))

    for child in node.get("children", []) or []:
        _serialize_accessibility_tree(child, lines=lines, depth=depth + 1)

    return "\n".join(lines)


def _get_accessibility_tree(page) -> dict[str, Any]:  # noqa: ANN001, ANN201
    raw_tree = None

    try:
        raw_tree = page.accessibility.snapshot(interesting_only=True)
    except Exception:
        raw_tree = None

    if raw_tree is None:
        raw_tree = page.evaluate(
            """
            () => {
              function roleOf(el) {
                return (
                  el.getAttribute("role") ||
                  (el.tagName ? el.tagName.toLowerCase() : "")
                );
              }

              function nameOf(el) {
                return (
                  el.getAttribute("aria-label") ||
                  el.innerText ||
                  el.textContent ||
                  el.value ||
                  ""
                ).trim();
              }

              function walk(el, depth = 0) {
                if (!el || depth > 6) return null;
                const node = {
                  role: roleOf(el),
                  name: nameOf(el).slice(0, 200),
                  children: [],
                };
                for (const child of Array.from(el.children || []).slice(0, 20)) {
                  const childNode = walk(child, depth + 1);
                  if (childNode) {
                    node.children.push(childNode);
                  }
                }
                if (!node.role && !node.name && node.children.length === 0) {
                  return null;
                }
                return node;
              }

              return walk(document.body);
            }
            """
        )

    compact_tree = _trim_accessibility_tree(raw_tree) or {"role": "document", "name": "empty"}
    return {
        "tree": compact_tree,
        "summary": _shorten(_serialize_accessibility_tree(compact_tree), _MAX_TEXT_CHARS),
    }


def _snapshot_page(page) -> dict[str, Any]:  # noqa: ANN001
    title = page.title()
    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        try:
            body_text = page.text_content("body", timeout=3000) or ""
        except Exception:
            body_text = ""

    accessibility = _get_accessibility_tree(page)

    elements = page.evaluate(
        f"""
        () => {{
          const limit = {_MAX_ELEMENTS};
          const items = [];
          const nodes = Array.from(document.querySelectorAll(
            "a, button, input, textarea, select, [role='button'], [onclick]"
          ));

          function textOf(el) {{
            return (el.innerText || el.textContent || el.getAttribute("aria-label") || el.value || "").trim();
          }}

          function roleOf(el) {{
            return (
              el.getAttribute("role") ||
              (el.tagName === "A" ? "link" : "") ||
              (el.tagName === "BUTTON" ? "button" : "") ||
              (el.tagName === "INPUT" ? "input" : "") ||
              (el.tagName ? el.tagName.toLowerCase() : "")
            );
          }}

          function cssSelector(el) {{
            if (!el || !el.tagName) return "";
            if (el.id) return `#${{el.id}}`;
            const name = el.getAttribute("name");
            if (name) return `${{el.tagName.toLowerCase()}}[name="${{name}}"]`;
            const testId = el.getAttribute("data-testid");
            if (testId) return `${{el.tagName.toLowerCase()}}[data-testid="${{testId}}"]`;
            const aria = el.getAttribute("aria-label");
            if (aria) return `${{el.tagName.toLowerCase()}}[aria-label="${{aria}}"]`;
            const cls = (el.className || "").toString().trim().split(/\\s+/).filter(Boolean).slice(0, 2);
            if (cls.length) return `${{el.tagName.toLowerCase()}}.${{cls.join(".")}}`;
            const parent = el.parentElement;
            if (!parent) return el.tagName.toLowerCase();
            const siblings = Array.from(parent.children).filter(node => node.tagName === el.tagName);
            const index = siblings.indexOf(el) + 1;
            return `${{el.tagName.toLowerCase()}}:nth-of-type(${{index}})`;
          }}

          for (const el of nodes) {{
            if (items.length >= limit) break;
            const text = textOf(el);
            const selector = cssSelector(el);
            if (!selector) continue;
            items.push({{
              role: roleOf(el),
              tag: (el.tagName || "").toLowerCase(),
              name: text.slice(0, 160),
              selector,
              aria_label: el.getAttribute("aria-label") || "",
              href: el.href || "",
            }});
          }}
          return items;
        }}
        """
    )

    return {
        "url": page.url,
        "title": title,
        "content": _shorten(body_text),
        "accessibility_tree": accessibility["tree"],
        "accessibility_summary": accessibility["summary"],
        "interactive_elements": elements if isinstance(elements, list) else [],
    }


def _success(action: str, page) -> dict[str, Any]:  # noqa: ANN001
    snapshot = _snapshot_page(page)
    return {
        "ok": True,
        "action": action,
        **snapshot,
    }


def _failure(action: str, error: Exception | str) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "error": str(error),
    }


@tool
def open_page(url: str) -> dict[str, Any]:
    """Open a webpage in Playwright. Plain text queries are converted into a DuckDuckGo search page."""

    try:
        target, mode = _resolve_target(url)
        runtime = _get_runtime()
        with _BROWSER_LOCK:
            runtime.page.goto(target, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT_MS)
            _wait_for_page_settle(runtime.page)
            result = _success("open_page", runtime.page)
            result["input"] = url
            result["mode"] = mode
            return result
    except Exception as exc:
        return _failure("open_page", exc)


@tool
def click_element(selector: str) -> dict[str, Any]:
    """Click a DOM element on the current page by CSS selector and return the new page snapshot."""

    try:
        if not (selector or "").strip():
            raise ValueError("selector is required")
        runtime = _get_runtime()
        with _BROWSER_LOCK:
            locator = runtime.page.locator(selector).first
            locator.wait_for(state="visible", timeout=_DEFAULT_TIMEOUT_MS)
            locator.click(timeout=_DEFAULT_TIMEOUT_MS)
            _wait_for_page_settle(runtime.page)
            result = _success("click_element", runtime.page)
            result["selector"] = selector
            return result
    except Exception as exc:
        return _failure("click_element", exc)


@tool
def get_page_content() -> dict[str, Any]:
    """Get a readable snapshot of the current page, including text and clickable element hints."""

    try:
        runtime = _get_runtime()
        with _BROWSER_LOCK:
            return _success("get_page_content", runtime.page)
    except Exception as exc:
        return _failure("get_page_content", exc)


@tool
def extract_info(selector: str) -> dict[str, Any]:
    """Extract text content from the matching DOM nodes on the current page."""

    try:
        if not (selector or "").strip():
            raise ValueError("selector is required")
        runtime = _get_runtime()
        with _BROWSER_LOCK:
            locator = runtime.page.locator(selector)
            count = locator.count()
            if count == 0:
                raise ValueError(f"no elements matched selector: {selector}")
            items: list[dict[str, Any]] = []
            for idx in range(min(count, 10)):
                node = locator.nth(idx)
                text = ""
                try:
                    text = node.inner_text(timeout=3000)
                except Exception:
                    text = node.text_content(timeout=3000) or ""
                items.append(
                    {
                        "index": idx,
                        "text": _shorten(text, 3000),
                    }
                )
            return {
                "ok": True,
                "action": "extract_info",
                "selector": selector,
                "url": runtime.page.url,
                "title": runtime.page.title(),
                "matches": count,
                "items": items,
            }
    except Exception as exc:
        return _failure("extract_info", exc)
