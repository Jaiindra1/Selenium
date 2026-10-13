"""Search URL patterns and CSS hints for commonly used online stores.

The adapters are intentionally small. Add a store here when its search route or
product-card HTML is known; unknown stores still use the generic browser flow.
"""

from typing import Any, Dict, Optional
from urllib.parse import quote_plus, urlparse


# Selectors are hints, not guarantees: store websites sometimes change them.
# The extraction engine has generic fallbacks when one of these selectors fails.
SITE_SELECTORS: Dict[str, Dict[str, Any]] = {
    "flipkart.com": {
        "product_links": 'a[href*="/p/"]',
        "titles": [".KzDlHZ", ".wjcEIp", "._4rR01T", "[class*='product-title']"],
        "prices": [".Nx9bqj", "._30jeq3", "[class*='price']"],
        "original_prices": [".yRaY8j", "._3I9_wc", "del", "s"],
        "ratings": [".XQDdHH", "._3LWZlK", "[class*='rating']"],
        "reviews": ["[class*='ratingCount']", "[class*='reviewCount']", "[class*='Wphh3N']"],
        "discounts": [".UkUFwK", "[class*='discount']"],
    },
    "amazon": {
        "product_links": "[data-component-type='s-search-result'] h2 a, a.a-link-normal.s-no-outline",
        "titles": ["h2 a span", "h2 span", "[class*='product-title']"],
        "prices": [".a-price .a-offscreen", "[class*='priceToPay']"],
        "original_prices": [".a-price.a-text-price .a-offscreen", "del", "s"],
        "ratings": [".a-icon-alt", "[aria-label*='out of 5']"],
        "reviews": [".s-underline-text", "[aria-label*='ratings']"],
        "discounts": ["[class*='savingsPercentage']"],
    },
    "ebay.com": {
        "product_links": "a.s-item__link",
        "titles": [".s-item__title", "h3"],
        "prices": [".s-item__price", "[class*='price']"],
        "original_prices": [".STRIKETHROUGH", "del", "s"],
        "ratings": [".x-star-rating span", "[aria-label*='out of 5']"],
        "reviews": [".s-item__reviews-count", "[class*='review']"],
        "discounts": ["[class*='discount']"],
    },
    "walmart.com": {
        "product_links": "a[href*='/ip/']",
        "titles": ["[data-automation-id='product-title']", "[data-testid='product-title']", "h2"],
        "prices": ["[data-automation-id='product-price']", "[itemprop='price']", "[class*='price']"],
        "original_prices": ["[data-testid='product-was-price']", "del", "s"],
        "ratings": ["[data-testid='product-ratings']", "[aria-label*='stars']"],
        "reviews": ["[data-testid='product-reviews']", "[class*='review']"],
        "discounts": ["[class*='savings']", "[class*='discount']"],
    },
    "etsy.com": {
        "product_links": "a[href*='/listing/']",
        "titles": ["h3", ".v2-listing-card__title", "[class*='listing-title']"],
        "prices": [".currency-value", "[class*='currency-value']", "[class*='price']"],
        "original_prices": ["del", "s", "[class*='original-price']"],
        "ratings": ["[aria-label*='stars']", "[class*='rating']"],
        "reviews": ["[class*='review']"],
        "discounts": ["[class*='discount']"],
    },
    "target.com": {
        "product_links": "a[href*='/p/']",
        "titles": ["[data-test='product-title']", "h3", "[class*='ProductTitle']"],
        "prices": ["[data-test='current-price']", "[data-test='product-price']", "[class*='Price']"],
        "original_prices": ["[data-test='comparison-price']", "del", "s"],
        "ratings": ["[data-test='rating']", "[aria-label*='stars']"],
        "reviews": ["[data-test='ratingCount']", "[class*='ratingCount']"],
        "discounts": ["[class*='discount']", "[class*='promotion']"],
    },
    "bestbuy.com": {
        "product_links": "a[href*='/site/']",
        "titles": [".sku-title", "h4", "[class*='product-title']"],
        "prices": [".priceView-customer-price span", "[class*='priceView-customer-price']"],
        "original_prices": [".priceView-previous-price", "del", "s"],
        "ratings": [".rating-none", "[aria-label*='stars']", "[class*='rating']"],
        "reviews": [".c-reviews", "[class*='review-count']"],
        "discounts": ["[class*='savings']", "[class*='discount']"],
    },
}


def _normalise_host(website: str) -> str:
    """Extract a lowercase host without a leading ``www.`` prefix."""
    host = urlparse(website).netloc.lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _matches_domain(host: str, domain: str) -> bool:
    """Return True for the domain itself or one of its subdomains."""
    return host == domain or host.endswith("." + domain)


def get_site_selectors(website: str) -> Dict[str, Any]:
    """Return selector hints for a supported store, or an empty dictionary."""
    host = _normalise_host(website)

    # Check specific domains before generic Amazon matches.
    for domain, selectors in SITE_SELECTORS.items():
        if domain == "amazon":
            if "amazon." in host:
                return selectors
        elif _matches_domain(host, domain):
            return selectors

    return {}


def build_search_url(website: str, query: str) -> Optional[str]:
    """Build a known store's search URL, or return None for generic handling.

    This avoids relying on the homepage search box for known stores. For an
    unfamiliar store, SearchService will try its visible search field instead.
    """
    parsed = urlparse(website)
    host = _normalise_host(website)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    encoded_query = quote_plus(query)

    # Flipkart's search-results route.
    if _matches_domain(host, "flipkart.com"):
        return f"{scheme}://{netloc}/search?q={encoded_query}"

    # Amazon regional domains use the same search parameter pattern.
    if "amazon." in host:
        return f"{scheme}://{netloc}/s?k={encoded_query}"

    # eBay search route.
    if _matches_domain(host, "ebay.com") or host.endswith("ebay.co.uk"):
        return f"{scheme}://{netloc}/sch/i.html?_nkw={encoded_query}"

    # Walmart search route.
    if _matches_domain(host, "walmart.com"):
        return f"{scheme}://{netloc}/search?q={encoded_query}"

    # Etsy search route.
    if _matches_domain(host, "etsy.com"):
        return f"{scheme}://{netloc}/search?q={encoded_query}"

    # Target search route.
    if _matches_domain(host, "target.com"):
        return f"{scheme}://{netloc}/s?searchTerm={encoded_query}"

    # Best Buy search route.
    if _matches_domain(host, "bestbuy.com"):
        return f"{scheme}://{netloc}/site/searchpage.jsp?st={encoded_query}"

    # Return None so unknown sites use their own visible search form.
    return None
