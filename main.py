"""Command-line entry point for the modular e-commerce product scraper."""

from pprint import pprint
from urllib.parse import urlparse

from browser_manager import create_driver
from config import MAX_PRODUCTS
from pdf_report import generate_pdf_report
from product_extractor import extract_products
from product_filter import filter_products
from search_service import page_needs_manual_attention, search_website


def normalise_website(website: str) -> str:
    """Ensure the input URL has a scheme and a valid host before opening it."""
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    parsed = urlparse(website)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError("Enter a valid website, for example https://www.example.com")

    return website


def print_products(products) -> None:
    """Print the extracted data as a Python list of dictionaries."""
    print("\nExtracted product data:")
    # Convert dataclasses into dictionaries so output is easy to copy or inspect.
    pprint([product.to_dict() for product in products], sort_dicts=False, width=120)


def main() -> None:
    """Run the browser, search a store, extract products, and download a PDF report."""
    # Ask the user which online store should be searched.
    website_input = input("Enter e-commerce website (for example Flipkart.com): ").strip()
    try:
        website = normalise_website(website_input)
    except ValueError as error:
        print(f"Input error: {error}")
        return

    # Open the browser through a dedicated module so browser setup stays reusable.
    driver = create_driver()

    try:
        print("\nOpening website...")
        driver.get(website)
        print("Website title:", driver.title)
        print("Website URL:", driver.current_url)

        # Ask for the product only after the browser has opened the requested site.
        query = input("\nEnter product to search for: ").strip()
        if not query:
            print("No search term entered; no products were collected.")
            report_path = generate_pdf_report([], "(empty query)", website)
            print("PDF report downloaded to:", report_path)
            return

        # SearchService chooses a known store route or interacts with a generic search field.
        result_url = search_website(driver, website, query)
        print("Search results URL:", result_url)

        # Do not bypass anti-bot challenges. Allow the user to handle the page manually.
        if page_needs_manual_attention(driver):
            print(
                "The page appears to show a verification/security step. "
                "Complete it manually in Chrome if you are permitted to access the site."
            )
            input("After the page is ready, press Enter to continue scraping... ")

        # Selenium returns the rendered DOM, including many JavaScript-rendered elements.
        rendered_html = driver.page_source
        extracted_products = extract_products(rendered_html, driver.current_url, MAX_PRODUCTS)
        products = filter_products(extracted_products, query)
        print(f"Filtered {len(extracted_products)} extracted items to {len(products)} relevant products.")

        # Print the list in the terminal before creating the PDF file.
        print_products(products)

        # The scraper always writes a PDF, even when zero product cards were found.
        report_path = generate_pdf_report(products, query, website)
        print(f"\nTotal products extracted: {len(products)}")
        print("PDF report downloaded to:", report_path.resolve())

        if not products:
            print(
                "Tip: check the open Chrome page. If products are visible but none were "
                "extracted, add selectors for that store in site_adapters.py."
            )

    except KeyboardInterrupt:
        # Treat Ctrl+C as a user cancellation rather than an unexplained crash.
        print("\nScraping cancelled by user.")
    except Exception as error:
        # Show a useful failure message while ensuring Chrome still closes below.
        print(f"\nScraping failed: {type(error).__name__}: {error}")
    finally:
        # Quit exactly once to release Chrome and its persistent profile lock.
        driver.quit()
        print("Browser closed. Task completed.")


# Run the interactive command-line flow only when this file is executed directly.
if __name__ == "__main__":
    main()
