import logging
import re
import typing as ta

from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from curl_cffi import requests as curl_requests

from newsletter.constants import TRACKERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

playwright_ctx = None
browser = None
context = None


def init_playwright_browser():
    global playwright_ctx, browser, context
    if playwright_ctx is None:
        playwright_ctx = sync_playwright().start()
        browser = playwright_ctx.chromium.launch(headless=True)
        context = browser.new_context()


def resolve_redirect_impersonate(url: str, timeout: float = 15.0) -> str:
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        logger.warning(f"Invalid URL scheme: '{url}'.")
        return url
    try:
        # Impersonate a recent Chrome version. Others like 'chrome110', 'firefox117' are possible.
        # Use allow_redirects=True (default)
        response = curl_requests.get(url, impersonate="chrome116", timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url

        if any(t in final_url for t in TRACKERS):
            final_url = resolve_redirect_with_playwright(url, timeout=timeout)
            logger.info(f"Resolved via Playwright: {url} → {final_url}")
            return final_url

        logger.info(f"Resolved via curl_cffi: {url} → {final_url}")
        return final_url

    except Exception as e:
        logger.warning(f"curl_cffi failed for {url}: {e}")

    return url


def resolve_redirect_with_playwright(url: str, timeout: float = 15.0) -> str:
    try:
        init_playwright_browser()
        page = context.new_page()
        page.goto(url, timeout=timeout * 1000)
        final_url = page.url
        page.close()
        return final_url
    except Exception as e:
        logger.warning(f"Playwright failed for {url}: {e}")
        return url


def resolve_redirect_from_known_sources(url: str, trackers: ta.List[str] = TRACKERS, timeout: float = 10.0) -> str:
    """
    Resolves a redirect-tracking URL if its domain is in the provided trackers list.
    """
    if url and any(tracker_domain in url for tracker_domain in trackers):
        return resolve_redirect_impersonate(url, timeout=timeout)
    return url


def strip_tracking_params(url: str, allowed_params=None) -> str:
    """
    Removes common tracking query parameters like utm_* from a URL.
    """
    if allowed_params is None:
        allowed_params = set()  # e.g., allowlist like {"ref"} if needed

    parsed = urlparse(url)
    clean_query = {
        k: v for k, v in parse_qs(parsed.query).items()
        if not k.lower().startswith("utm_") and k not in allowed_params
    }
    new_query = urlencode(clean_query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def resolve_links_in_body(body: str) -> str:
    """
    Finds and resolves Beehiiv-style or standalone https URLs in text,
    removing tracking parameters if present.
    """
    pattern = re.compile(r"<(https://[^>\s]+)>|(?<!href=\")\b(https://[^\s<>\"']+)\b")
    found_links = set(match.group(1) or match.group(2) for match in pattern.finditer(body))

    replacements = {}
    for url in found_links:
        try:
            resolved = resolve_redirect_from_known_sources(url)
            stripped = strip_tracking_params(resolved)
            replacements[url] = stripped
        except Exception as e:
            print(f"[warn] Could not resolve: {url} — {e}")
            replacements[url] = url

    def replacer(match):
        original = match.group(1) or match.group(2)
        resolved = replacements.get(original, original)
        return f"<{resolved}>" if match.group(1) else resolved

    return pattern.sub(replacer, body)
