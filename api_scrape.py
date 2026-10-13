"""Non-interactive JSON entry point used by the Node.js API."""

import json
import sys
import tempfile
from pathlib import Path

from browser_manager import create_driver
from config import MAX_PRODUCTS
from main import normalise_website
from pdf_report import generate_pdf_report
from product_extractor import extract_products
from search_service import page_needs_manual_attention, search_website


def run(website_input: str, query: str) -> dict:
    website = normalise_website(website_input)
    query = query.strip()
    if not query:
        raise ValueError("A product search term is required")

    with tempfile.TemporaryDirectory(prefix="dealscope-chrome-") as profile:
        driver = create_driver(profile_dir=Path(profile), headless=True)
        try:
            driver.get(website)
            result_url = search_website(driver, website, query)
            if page_needs_manual_attention(driver):
                raise RuntimeError(
                    "The store requested a CAPTCHA, login, or verification step that cannot be completed in headless mode."
                )
            products = extract_products(driver.page_source, driver.current_url, MAX_PRODUCTS)
            report_path = generate_pdf_report(products, query, website)
            return {
                "website": website,
                "query": query,
                "resultUrl": result_url,
                "products": [product.to_dict() for product in products],
                "reportPath": str(report_path.resolve()),
            }
        finally:
            driver.quit()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: api_scrape.py <website> <query>")
        print(json.dumps({"ok": True, "data": run(sys.argv[1], sys.argv[2])}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        sys.exit(1)
