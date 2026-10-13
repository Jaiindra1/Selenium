"""Navigate to product results on known and unfamiliar e-commerce sites."""

import time
from typing import Optional
from urllib.parse import quote_plus, urlparse, urlunparse

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from config import ELEMENT_WAIT_SECONDS, RESULT_RENDER_WAIT_SECONDS
from site_adapters import build_search_url


def _wait_for_page(driver) -> None:
    """Wait for the browser's document to become interactive or complete."""
    try:
        WebDriverWait(driver, ELEMENT_WAIT_SECONDS).until(
            lambda browser: browser.execute_script(
                "return document.readyState"
            ) in ("interactive", "complete")
        )
    except (TimeoutException, WebDriverException):
        # Some sites keep loading trackers forever; usable page HTML may exist.
        pass

    # Allow JavaScript-rendered result cards a short time to appear.
    time.sleep(RESULT_RENDER_WAIT_SECONDS)


def _score_search_field(element) -> int:
    """Score an input based on hints that it is the site's search field."""
    score = 0

    # Read common attributes used by web developers to label search inputs.
    attributes = " ".join(
        str(element.get_attribute(name) or "")
        for name in ("type", "name", "id", "placeholder", "aria-label", "title")
    ).lower()

    # Exact search input types are stronger signals than generic text inputs.
    input_type = (element.get_attribute("type") or "").lower()
    if input_type == "search":
        score += 10

    # Input attributes frequently contain words such as search, query, or product.
    for keyword, points in (
        ("search", 8),
        ("query", 6),
        ("keyword", 5),
        ("product", 3),
        ("find", 2),
    ):
        if keyword in attributes:
            score += points

    # Prefer a field whose containing form looks like a search form.
    try:
        form_action = (element.find_element(By.XPATH, "ancestor::form").get_attribute("action") or "").lower()
        if "search" in form_action or "query" in form_action:
            score += 4
    except WebDriverException:
        # An input may not be inside a form, which is common on modern sites.
        pass

    return score


def _find_search_field(driver):
    """Return the highest-scoring visible and enabled search-like input.

    Returns None when no plausible search field can be found. The caller then
    tries a conventional /search?q=... route as a generic fallback.
    """
    # Search boxes may be input elements, textareas, or ARIA searchbox widgets.
    candidates = driver.find_elements(
        By.CSS_SELECTOR,
        "input, textarea, [role='searchbox'], [contenteditable='true']",
    )

    ranked = []
    for element in candidates:
        # Hidden fields and form controls should never be used for text entry.
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            input_type = (element.get_attribute("type") or "").lower()
            if input_type in {"hidden", "submit", "button", "checkbox", "radio", "password", "file", "email", "tel", "number", "date"}:
                continue

            # Keep even generic text fields as low-scoring candidates; some stores
            # do not expose a useful placeholder or accessible label.
            ranked.append((_score_search_field(element), element))
        except WebDriverException:
            # The DOM can change while a page is rendering; skip stale elements.
            continue

    if not ranked:
        return None

    # Highest score first. A zero-score field is still usable if it is the only one.
    ranked.sort(key=lambda entry: entry[0], reverse=True)
    return ranked[0][1]


def _submit_generic_search(driver, query: str) -> bool:
    """Use a visible search field on an unfamiliar store and submit the query."""
    field = _find_search_field(driver)
    if field is None:
        return False

    # Replace any default text, enter the user's query, and press Enter.
    field.click()
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(query)
    field.send_keys(Keys.ENTER)

    # Wait for URL or page content to change. Some sites update results in place.
    try:
        WebDriverWait(driver, ELEMENT_WAIT_SECONDS).until(
            lambda browser: query.lower() in browser.current_url.lower()
            or browser.execute_script("return document.readyState") == "complete"
        )
    except (TimeoutException, WebDriverException):
        # Continue to inspect the current page even if this condition timed out.
        pass

    _wait_for_page(driver)
    return True


def search_website(driver, website: str, query: str) -> str:
    """Search a store using a known route or its own visible search form.

    The return value is the final URL after the search attempt. If the site is
    not in site_adapters.py, a standard /search?q=... route is attempted only
    when no visible search input can be found.
    """
    # Prefer a known adapter because direct search URLs are more consistent.
    known_search_url = build_search_url(website, query)
    if known_search_url:
        print(f"Using the store's configured search route: {known_search_url}")
        driver.get(known_search_url)
        _wait_for_page(driver)
        return driver.current_url

    # Unknown store: use the real search field in the page instead of assuming
    # all websites have the same URL pattern.
    print("No built-in search route for this store; looking for its search box...")
    if _submit_generic_search(driver, query):
        return driver.current_url

    # Some stores use a standard search endpoint (notably many Shopify stores).
    # This is only a fallback; a store may use a different URL pattern.
    parsed = urlparse(website)
    fallback_url = urlunparse((
        parsed.scheme or "https",
        parsed.netloc,
        "/search",
        "",
        "q=" + quote_plus(query),
        "",
    ))
    print("No visible search box was detected; trying a common /search?q= route.")
    driver.get(fallback_url)
    _wait_for_page(driver)
    return driver.current_url


def page_needs_manual_attention(driver) -> bool:
    """Detect common verification/interstitial messages without bypassing them."""
    # Read only rendered page text; do not try to defeat any anti-bot challenge.
    body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
    warning_phrases = (
        "verify you are human",
        "verify you're human",
        "unusual traffic",
        "robot check",
        "captcha",
        "access denied",
        "security challenge",
    )
    return any(phrase in body_text for phrase in warning_phrases)
