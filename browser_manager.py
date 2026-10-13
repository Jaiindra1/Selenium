"""Create and configure the Selenium Chrome browser."""

import os

from pathlib import Path
from typing import Optional

from selenium import webdriver

from config import (
    CHROME_PROFILE_DIR,
    HEADLESS,
    PAGE_LOAD_TIMEOUT_SECONDS,
)


def create_driver(
    profile_dir: Optional[Path] = None,
    headless: Optional[bool] = None,
) -> webdriver.Chrome:
    """Start Chrome with one dedicated, reusable profile.

    The browser remains visible by default so a user can handle cookie dialogs,
    login requirements, or verification pages manually. Selenium Manager normally
    locates the matching driver automatically with recent Selenium versions.
    """
    # Use project defaults unless the caller explicitly supplies alternatives.
    selected_profile = Path(profile_dir or CHROME_PROFILE_DIR)
    selected_headless = HEADLESS if headless is None else headless

    # Create the profile directory before Chrome attempts to open it.
    selected_profile.mkdir(parents=True, exist_ok=True)

    # Configure Chrome without reusing the user's everyday browser profile.
    options = webdriver.ChromeOptions()
    chrome_binary = os.getenv("CHROME_BIN")
    if chrome_binary:
        options.binary_location = chrome_binary
    options.add_argument(f"--user-data-dir={selected_profile}")
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    # Headless mode is optional and disabled by default for manual intervention.
    if selected_headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1200")

    # Launch Chrome and set a maximum navigation wait to avoid hanging forever.
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)

    return driver
