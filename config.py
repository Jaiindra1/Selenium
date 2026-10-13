"""Central settings for the multi-store product scraper.

Keep paths, timeouts, and limits here so that they can be changed without
editing the scraping or PDF-reporting modules.
"""

from pathlib import Path

# Resolve the project directory from this file, not from the shell's working directory.
PROJECT_DIR = Path(__file__).resolve().parent

# Use a dedicated persistent Chrome profile so cookies/session state can persist.
# Do not point this at your everyday Chrome profile; Chrome can lock it while in use.
CHROME_PROFILE_DIR = Path.home() / ".ecommerce_scraper" / "chrome_profile"

# Put generated product reports in the user's Downloads folder.
DOWNLOAD_DIR = Path.home() / "Downloads"

# Limits the time spent waiting for a page to load or a search form to react.
PAGE_LOAD_TIMEOUT_SECONDS = 35
ELEMENT_WAIT_SECONDS = 15
RESULT_RENDER_WAIT_SECONDS = 3

# Keep a large result page from producing an excessively large PDF by accident.
MAX_PRODUCTS = 100

# Leave the browser visible so the user can sign in, accept cookies, or solve a
# verification prompt manually if a website requires it.
HEADLESS = False
