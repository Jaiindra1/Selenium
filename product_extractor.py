"""Extract product records from structured metadata and product-card HTML.

The extractor is deliberately not tied to one marketplace. It first reads
Schema.org Product data (the most reliable cross-site format), then uses site
CSS hints and generic product-card heuristics to fill gaps.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from models import Product
from site_adapters import get_site_selectors


# Prices may use symbols before the amount or currency codes after the amount.
PRICE_PATTERN = re.compile(
    r"(?:₹|Rs\.?|INR|\$|US\$|€|£|A\$|C\$)\s*[\d,]+(?:\.\d{1,2})?"
    r"|[\d,]+(?:\.\d{1,2})?\s*(?:INR|USD|EUR|GBP)",
    re.IGNORECASE,
)

# Ratings and review counts appear in many different text formats.
RATING_PATTERN = re.compile(r"(?<!\d)([0-5](?:\.\d{1,2})?)\s*(?:/\s*5|out of 5|★|stars?)", re.I)
RATING_COUNT_PATTERN = re.compile(r"([\d,.]+\s*(?:ratings?|ratings? and reviews?))", re.I)
REVIEW_COUNT_PATTERN = re.compile(r"([\d,.]+\s*reviews?)", re.I)
DISCOUNT_PATTERN = re.compile(r"\b\d{1,2}\s*%\s*(?:off|discount)\b", re.I)


def _clean(value: Any) -> Optional[str]:
    """Convert a value to compact text; return None for empty values."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _first_value(value: Any) -> Optional[str]:
    """Take the first useful scalar from a string, list, or Schema.org object."""
    if isinstance(value, list):
        for item in value:
            result = _first_value(item)
            if result:
                return result
        return None
    if isinstance(value, dict):
        # ImageObject and Brand commonly wrap their visible value in these fields.
        for key in ("name", "url", "contentUrl", "value", "@id"):
            result = _first_value(value.get(key))
            if result:
                return result
        return None
    return _clean(value)


def _format_price(value: Any, currency: Optional[str] = None) -> Optional[str]:
    """Format a Schema.org price and its ISO currency code for display."""
    amount = _clean(value)
    if not amount:
        return None

    # Do not duplicate a currency code if the site's value already includes it.
    if currency and not re.search(r"[A-Za-z₹$€£]", amount):
        return f"{currency.upper()} {amount}"
    return amount


def _jsonld_objects(node: Any) -> Iterable[Dict[str, Any]]:
    """Yield every dictionary nested in a JSON-LD script, including @graph items."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _jsonld_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _jsonld_objects(value)


def _has_type(node: Dict[str, Any], expected: str) -> bool:
    """Check a Schema.org @type whether it is represented as text or a list."""
    value = node.get("@type", [])
    values = value if isinstance(value, list) else [value]
    return any(str(item).rsplit("/", 1)[-1].lower() == expected.lower() for item in values)


def _normalise_url(url: Optional[str]) -> str:
    """Remove query strings and fragments for duplicate detection only."""
    if not url:
        return ""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _offer_details(offers: Any) -> Dict[str, Optional[str]]:
    """Read price, currency, availability, and a possible original price from offers."""
    offer: Dict[str, Any] = {}

    # Offer may be a single object, a list of offers, or an AggregateOffer.
    if isinstance(offers, list):
        offer = next((item for item in offers if isinstance(item, dict)), {})
    elif isinstance(offers, dict):
        offer = offers

    currency = _clean(offer.get("priceCurrency"))
    price_value = offer.get("price")

    # AggregateOffer often exposes lowPrice/highPrice instead of price.
    if price_value is None:
        price_value = offer.get("lowPrice") or offer.get("priceSpecification")
    if isinstance(price_value, dict):
        price_value = price_value.get("price")

    # AggregateOffer.highPrice is usually the top of a price range, not an MRP.
    # Do not mislabel it as an original/sale price; visible card markup handles MRP.
    old_price = None
    availability = _first_value(offer.get("availability"))
    if availability:
        availability = availability.rsplit("/", 1)[-1]

    return {
        "price": _format_price(price_value, currency),
        "original_price": _format_price(old_price, currency),
        "currency": currency,
        "availability": availability,
    }


def _product_from_jsonld(node: Dict[str, Any], page_url: str) -> Optional[Product]:
    """Convert a Schema.org Product object into the shared Product data model."""
    product_type = _has_type(node, "Product") or _has_type(node, "ProductGroup")
    if not product_type:
        return None

    name = _first_value(node.get("name"))
    if not name:
        return None

    # Find the best product destination URL exposed in structured metadata.
    product_url = _first_value(node.get("url")) or _first_value(node.get("@id")) or page_url
    product_url = urljoin(page_url, product_url)

    offers = _offer_details(node.get("offers"))
    aggregate = node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}

    # Read extra properties published by some product pages.
    specifications: List[str] = []
    extra_properties = node.get("additionalProperty", [])
    if isinstance(extra_properties, dict):
        extra_properties = [extra_properties]
    if isinstance(extra_properties, list):
        for prop in extra_properties:
            if not isinstance(prop, dict):
                continue
            key = _clean(prop.get("name"))
            value = _first_value(prop.get("value"))
            if key and value:
                specifications.append(f"{key}: {value}")

    brand = _first_value(node.get("brand"))
    image_url = _first_value(node.get("image"))

    return Product(
        name=name,
        product_url=product_url,
        price=offers["price"],
        original_price=offers["original_price"],
        currency=offers["currency"],
        rating=_clean(aggregate.get("ratingValue")),
        ratings_count=_clean(aggregate.get("ratingCount")),
        reviews_count=_clean(aggregate.get("reviewCount")),
        availability=offers["availability"],
        brand=brand,
        description=_first_value(node.get("description")),
        specifications=specifications,
        image_url=urljoin(page_url, image_url) if image_url else None,
        source_site=urlparse(page_url).netloc,
    )


def _extract_jsonld(soup: BeautifulSoup, page_url: str) -> List[Product]:
    """Extract Product objects from application/ld+json scripts on the page."""
    products: List[Product] = []
    seen = set()

    # JSON-LD scripts are machine-readable product metadata when the site provides them.
    for script in soup.select('script[type="application/ld+json"]'):
        raw_json = script.string or script.get_text(strip=True)
        if not raw_json:
            continue

        try:
            payload = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            # Skip malformed scripts without losing data from the rest of the page.
            continue

        for node in _jsonld_objects(payload):
            product = _product_from_jsonld(node, page_url)
            if not product:
                continue

            key = (_normalise_url(product.product_url), product.name.lower())
            if key in seen:
                continue
            seen.add(key)
            products.append(product)

    return products


def _select_text(card: Tag, selectors: Sequence[str]) -> Optional[str]:
    """Return text from the first CSS selector that finds non-empty content."""
    for selector in selectors:
        try:
            element = card.select_one(selector)
        except Exception:
            # A malformed/custom selector should not abort all extraction.
            continue
        if element:
            text = _clean(element.get_text(" ", strip=True))
            if text:
                return text
            # Amazon and some other sites store product text in an aria label.
            text = _clean(element.get("aria-label") or element.get("title"))
            if text:
                return text
    return None


def _find_product_card(link: Tag) -> Optional[Tag]:
    """Find the nearest ancestor that looks like one product card, not the page."""
    current = link

    # Walk upward a limited number of levels so one card does not become the whole grid.
    for _ in range(9):
        parent = current.parent
        if not isinstance(parent, Tag):
            return None
        current = parent

        text = current.get_text(" ", strip=True)
        if not text or len(text) > 2400:
            continue

        has_price = bool(PRICE_PATTERN.search(text))
        has_image_or_heading = bool(current.select_one("img, h1, h2, h3, h4, [role='heading']"))
        if has_price and has_image_or_heading:
            return current

    return None


def _extract_price_text(card: Tag, selectors: Dict[str, Any]) -> Optional[str]:
    """Prefer a site's known price selector, then fall back to currency patterns."""
    value = _select_text(card, selectors.get("prices", []))
    if value:
        return value

    text = card.get_text(" ", strip=True)
    match = PRICE_PATTERN.search(text)
    return match.group(0).strip() if match else None


def _extract_card_title(card: Tag, link: Tag, selectors: Dict[str, Any]) -> Optional[str]:
    """Find a product name from known selectors, headings, link text, or image alt."""
    # Store-specific title selectors are the most precise option.
    title = _select_text(card, selectors.get("titles", []))
    if title:
        return title

    # Product cards commonly use heading elements for titles.
    heading = card.select_one("h1, h2, h3, h4, [role='heading']")
    if heading:
        heading_text = _clean(heading.get_text(" ", strip=True))
        if heading_text:
            return heading_text

    # The clickable product title is often the anchor text or its title attribute.
    for value in (
        link.get_text(" ", strip=True),
        link.get("title"),
        link.get("aria-label"),
    ):
        cleaned = _clean(value)
        if cleaned and len(cleaned) > 2:
            return cleaned

    # Image links sometimes have no visible text but do include useful alt text.
    image = link.select_one("img") or card.select_one("img[alt]")
    if image:
        return _clean(image.get("alt"))

    return None


def _extract_specifications(card: Tag, title: Optional[str]) -> List[str]:
    """Collect short bullet/specification texts without repeating the title or price."""
    candidates: List[str] = []

    # List items often contain specifications; store themes may expose feature classes.
    for element in card.select("li, [class*='specification'], [class*='feature']"):
        value = _clean(element.get_text(" ", strip=True))
        if not value or value == title or len(value) > 240:
            continue
        if PRICE_PATTERN.search(value) or DISCOUNT_PATTERN.search(value):
            continue
        if value not in candidates:
            candidates.append(value)

    # Restrict output length so PDF reports remain readable.
    return candidates[:12]


def _product_from_card(link: Tag, page_url: str, selectors: Dict[str, Any]) -> Optional[Product]:
    """Convert a product link and its nearest product-card ancestor into Product."""
    href = _clean(link.get("href"))
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    # Resolve relative product hrefs into absolute links suitable for the report.
    product_url = urljoin(page_url, href)
    page_host = urlparse(page_url).netloc.lower().removeprefix("www.")
    product_host = urlparse(product_url).netloc.lower().removeprefix("www.")

    # Ignore external navigation, ads, and partner-site links.
    if product_host and page_host and product_host != page_host:
        return None

    # A link should be attached to a card with both a price and product imagery/title.
    card = _find_product_card(link)
    if not card:
        return None

    name = _extract_card_title(card, link, selectors)
    price = _extract_price_text(card, selectors)
    if not name or not price:
        return None

    # An optional product original price can come from a known selector or second price.
    original_price = _select_text(card, selectors.get("original_prices", []))
    all_prices = PRICE_PATTERN.findall(card.get_text(" ", strip=True))
    if not original_price and len(all_prices) > 1 and all_prices[1] != price:
        original_price = all_prices[1]

    # Ratings, reviews, and discount details use store selectors followed by text patterns.
    rating = _select_text(card, selectors.get("ratings", []))
    reviews_text = _select_text(card, selectors.get("reviews", []))
    discount = _select_text(card, selectors.get("discounts", []))
    card_text = card.get_text(" ", strip=True)

    if not rating:
        match = RATING_PATTERN.search(card_text)
        rating = match.group(1) if match else None

    ratings_count = None
    reviews_count = None
    if reviews_text:
        match = REVIEW_COUNT_PATTERN.search(reviews_text)
        reviews_count = match.group(1) if match else reviews_text
        match = RATING_COUNT_PATTERN.search(reviews_text)
        ratings_count = match.group(1) if match else None

    if not reviews_count:
        match = REVIEW_COUNT_PATTERN.search(card_text)
        reviews_count = match.group(1) if match else None
    if not ratings_count:
        match = RATING_COUNT_PATTERN.search(card_text)
        ratings_count = match.group(1) if match else None
    if not discount:
        match = DISCOUNT_PATTERN.search(card_text)
        discount = match.group(0) if match else None

    # Read image URLs from common lazy-loading attributes used by shopping sites.
    image = link.select_one("img") or card.select_one("img")
    image_url = None
    if image:
        image_url = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
            or image.get("srcset", "").split(",")[0].strip().split(" ")[0]
        )
        if image_url:
            image_url = urljoin(page_url, image_url)

    return Product(
        name=name,
        product_url=product_url,
        price=price,
        original_price=original_price,
        discount=discount,
        rating=rating,
        ratings_count=ratings_count,
        reviews_count=reviews_count,
        specifications=_extract_specifications(card, name),
        image_url=image_url,
        source_site=urlparse(page_url).netloc,
    )


def extract_products(html: str, page_url: str, max_products: int = 100) -> List[Product]:
    """Extract and deduplicate products from the rendered page HTML.

    JSON-LD and visible cards are merged. This means a result can still have
    ratings/specifications from structured data if its visual card is incomplete.
    """
    soup = BeautifulSoup(html, "html.parser")
    selectors = get_site_selectors(page_url)

    # Start with structured metadata, which is generally more stable than CSS classes.
    structured_products = _extract_jsonld(soup, page_url)

    # Gather likely product links from a store-specific selector plus a generic fallback.
    candidate_links: List[Tag] = []
    selector = selectors.get("product_links")
    if selector:
        try:
            candidate_links.extend(soup.select(selector))
        except Exception:
            # If a store changes its HTML, generic anchors can still work.
            pass
    candidate_links.extend(soup.select("a[href]"))

    dom_products: List[Product] = []
    seen_dom_urls = set()
    for link in candidate_links:
        product = _product_from_card(link, page_url, selectors)
        if not product:
            continue

        key = _normalise_url(product.product_url)
        if key in seen_dom_urls:
            continue
        seen_dom_urls.add(key)
        dom_products.append(product)

        # Respect the configurable cap while traversing large pages.
        if len(dom_products) >= max_products:
            break

    # Merge structured and DOM data by URL. DOM data fills only missing fields.
    products_by_key: Dict[str, Product] = {}
    page_key = _normalise_url(page_url)
    for product in structured_products + dom_products:
        key = _normalise_url(product.product_url) or product.name.lower()
        # If several structured products omit URLs, avoid merging them all into
        # the current search page URL; include each product name in that case.
        if key == page_key:
            key = f"{key}::{product.name.lower()}"
        if key not in products_by_key:
            products_by_key[key] = product
            continue

        existing = products_by_key[key]
        # Prefer values already found; use the second record only to fill gaps.
        for field_name in (
            "price", "original_price", "currency", "discount", "rating",
            "ratings_count", "reviews_count", "availability", "brand",
            "description", "image_url", "source_site",
        ):
            if not getattr(existing, field_name) and getattr(product, field_name):
                setattr(existing, field_name, getattr(product, field_name))
        if not existing.specifications and product.specifications:
            existing.specifications = product.specifications
        if not existing.product_url and product.product_url:
            existing.product_url = product.product_url

    # Return at most the requested number of products in extraction order.
    return list(products_by_key.values())[:max_products]
