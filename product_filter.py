"""Relevance filtering applied after Selenium extracts a store's result page."""

import re
from typing import Iterable, List

from models import Product


CATEGORIES = {
    "mobile": {
        "queries": {"mobile", "mobiles", "phone", "phones", "smartphone", "smartphones"},
        "positive": {"mobile", "phone", "smartphone", "iphone", "galaxy", "pixel", "oneplus", "redmi", "realme", "vivo", "oppo", "motorola", "nothing phone"},
        "negative": {"case", "cover", "charger", "cable", "screen guard", "tempered glass", "holder", "stand", "skin", "earphone", "headphone", "battery", "adapter"},
    },
    "laptop": {
        "queries": {"laptop", "laptops", "notebook", "notebooks"},
        "positive": {"laptop", "notebook", "macbook", "chromebook", "vivobook", "thinkpad", "ideapad"},
        "negative": {"bag", "sleeve", "charger", "stand", "keyboard", "mouse", "skin", "adapter"},
    },
    "tv": {
        "queries": {"tv", "tvs", "television", "televisions"},
        "positive": {"tv", "television", "smart tv", "led tv", "oled", "qled"},
        "negative": {"remote", "stand", "mount", "cover", "cable", "adapter"},
    },
    "headphones": {
        "queries": {"headphone", "headphones", "earphone", "earphones", "earbuds", "headset"},
        "positive": {"headphone", "headphones", "earphone", "earphones", "earbuds", "headset", "tws"},
        "negative": {"case", "cover", "cable", "ear pads", "ear cushions", "adapter", "stand"},
    },
}

STOP_WORDS = {
    "a", "an", "and", "the", "for", "with", "in", "on", "of", "to", "buy", "best", "new",
    "latest", "price", "prices", "online", "under", "below", "above", "from", "show", "me",
}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _product_text(product: Product) -> str:
    values = [product.name, product.brand, product.description, " ".join(product.specifications or [])]
    return _normalise(" ".join(str(value) for value in values if value))


def _query_tokens(query: str) -> List[str]:
    return [token for token in _normalise(query).split() if token not in STOP_WORDS and not token.isdigit()]


def _category_for(query: str):
    words = set(_normalise(query).split())
    return next((category for category in CATEGORIES.values() if words & category["queries"]), None)


def filter_products(products: Iterable[Product], query: str) -> List[Product]:
    """Keep products that match the requested category or specific model.

    Category-only queries accept products in that category but reject common
    accessories. Queries containing brand/model terms require every distinctive
    term, which prevents nearby recommendations from leaking into the results.
    """
    products = list(products)
    query_text = _normalise(query)
    category = _category_for(query)
    tokens = _query_tokens(query)
    category_words = category["queries"] if category else set()
    distinctive = [token for token in tokens if token not in category_words]
    # Numeric model identifiers matter (iPhone 15, S24, 1000XM5), but budget
    # values after "under/below/above" are price constraints, not model names.
    raw_words = query_text.split()
    model_numbers = re.findall(r"\b\d+[a-z]+\b|\b[a-z]+\d+[a-z0-9]*\b", query_text)
    model_numbers.extend(
        word for position, word in enumerate(raw_words)
        if word.isdigit() and (position == 0 or raw_words[position - 1] not in {"under", "below", "above", "upto", "within"})
    )
    distinctive.extend(token for token in model_numbers if token not in distinctive)

    ranked = []
    for index, product in enumerate(products):
        text = _product_text(product)
        if not text:
            continue
        if category:
            positive = any(term in text for term in category["positive"])
            accessory = any(term in text for term in category["negative"])
            if not positive or accessory:
                continue
        if distinctive and not all(token in text for token in distinctive):
            continue
        matches = sum(token in text for token in tokens)
        exact_bonus = 10 if query_text in text else 0
        ranked.append((exact_bonus + matches, -index, product))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked]
