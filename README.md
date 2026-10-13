# DealScope — E-commerce Product Research

DealScope is a full-stack web application for running product research against public e-commerce pages. It combines a React dashboard, a Node.js/Express API, SQLite search history, the existing Python/Selenium extraction engine, and downloadable PDF reports.

## Web application

### Stack

- React 19 and Vite frontend
- Node.js and Express API
- SQLite database (`better-sqlite3`)
- Python, Selenium, Beautiful Soup, and ReportLab scraping/report engine
- Docker deployment with headless Chromium

### Run locally

Install Node.js 22+, Python 3.10+, Google Chrome, and the Python requirements. Then run:

```bash
python -m pip install -r requirements.txt
npm install
npm run build
npm start
```

Open `http://localhost:3000`. For frontend hot reload during development, run `npm run dev` and open the Vite URL printed in the terminal.

Runtime data is saved under `data/` by default. Set `DATA_DIR`, `REPORT_DIR`, `PYTHON_BIN`, or `PORT` to override the defaults.

### Deploy on Render

The included `Dockerfile` installs Chromium and both application runtimes. The included `render.yaml` creates a Docker web service and a persistent disk for SQLite and PDF reports.

1. Push the repository to GitHub.
2. In Render, create a new Blueprint and select the repository.
3. Apply `render.yaml` and wait for the health check at `/api/health` to pass.

The configured persistent disk requires a paid Render instance. For a temporary demonstration you can remove the `disk` section, but search history and reports will disappear whenever the service restarts or redeploys.

## Original command-line scraper

This project opens a persistent Chrome profile, accepts a store URL and a product query, extracts product information from the rendered results page, prints a Python list of dictionaries, and downloads a timestamped PDF report to your Downloads folder.

## What it supports

- Known search routes for Flipkart, Amazon regional domains, eBay, Walmart, Etsy, Target, and Best Buy.
- Unknown stores through their visible search input, followed by a conventional `/search?q=...` fallback if no usable input is found.
- Product information from Schema.org `Product` JSON-LD metadata when the store publishes it.
- Generic HTML product cards, plus site selector hints in `site_adapters.py`.
- PDF output for both successful and empty extraction runs.
- One dedicated persistent Chrome profile, so cookies and login sessions can survive between runs.

**Important limitation:** there is no reliable way to scrape every e-commerce site using one universal selector. Stores differ in search routes, client-side rendering, product-card markup, authentication, regional behavior, and anti-bot controls. The generic extractor works where a site exposes standard metadata or recognizable product cards. Some stores will need a small adapter in `site_adapters.py`. This tool does not bypass CAPTCHAs, access controls, or security challenges.

## Project files

| File | Responsibility |
| --- | --- |
| `main.py` | Interactive command-line flow: asks for the store and product, prints results, downloads the PDF. |
| `config.py` | Chrome profile path, timeout settings, download directory, and result limits. |
| `browser_manager.py` | Chrome configuration and persistent profile creation. |
| `search_service.py` | Known-route navigation and generic search-box detection/submission. |
| `site_adapters.py` | Store-specific search URL patterns and CSS selector hints. |
| `product_extractor.py` | JSON-LD parsing, product-card heuristics, normalization, and deduplication. |
| `models.py` | Common `Product` data model used by every module. |
| `pdf_report.py` | Builds a readable PDF with product facts, specifications, and clickable URLs. |
| `tests/test_product_extractor.py` | Offline tests that do not open a browser. |

## Setup

Use Python 3.10 or later. Install a recent Google Chrome or Chromium build.

```bash
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

**Windows PowerShell**

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Recent Selenium releases include Selenium Manager, which usually finds the matching ChromeDriver automatically. If browser startup fails, update Selenium and Chrome, then try again.

## Run

From this project folder:

```bash
python main.py
```

Example prompts:

```text
Enter e-commerce website (for example Flipkart.com): Flipkart.com
Enter product to search for: Apple iPhone 17
```

The script prints the extracted records in the terminal and downloads the PDF to your user's `Downloads/` folder, for example:

```text
Downloads/product_report_Apple_iPhone_17_20261013_171700.pdf
```

The exact filename and data depend on the query and the live website. The sample filename above is only an illustration.

## Add support for another store

1. Open `site_adapters.py`.
2. Add a domain check in `build_search_url()` if the store uses a known search URL pattern. Return `None` if you prefer to use the store's own search input.
3. Add selector hints to `SITE_SELECTORS` for that domain, especially `product_links`, `titles`, `prices`, `original_prices`, `ratings`, `reviews`, and `discounts`.
4. Inspect the result page's HTML using Chrome DevTools. Selectors should point to a product card, not footer/navigation links.
5. Run `python -m unittest discover -s tests` and then test against the store in a normal browser session.

Prefer stable attributes such as `data-testid`, `data-automation-id`, and Schema.org metadata over frequently generated CSS class names.

## Output fields

Each item in the printed list is a dictionary with fields such as:

- `name`, `product_url`, `price`, `original_price`, `currency`, `discount`
- `rating`, `ratings_count`, `reviews_count`, `availability`
- `brand`, `description`, `specifications`, `image_url`, `source_site`

Fields the site does not publish are left as `None` or an empty list instead of being invented.

## PDF behavior

A PDF is downloaded even if no product is extracted. In that case the report explains that the loaded page may require manual login/cookie handling, may be a verification page, or may need a site-specific selector adapter. The PDF is placed in the user's `Downloads/` folder and includes a generation timestamp and clickable product URLs. A system font such as DejaVu Sans or Arial is used when available to support currency symbols.

## Responsible use

Use the scraper only on pages you are permitted to access. Respect each site's terms, robots guidance, privacy requirements, rate limits, and intellectual-property rules. Do not use it to access restricted personal data or circumvent a site's security mechanisms.
