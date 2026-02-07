"""
Playwright tests for remote-browser.

Tests browser functionality using Playwright via Chrome DevTools Protocol.
"""
import pytest
import time
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def wait_for_services():
    """Wait for services to start."""
    time.sleep(10)


@pytest.fixture(scope="function")
def browser_connection(wait_for_services):
    """Connect to remote browser via Chrome DevTools Protocol."""
    with sync_playwright() as p:
        # Connect to the remote browser via CDP
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        yield browser
        browser.close()


def test_open_google_and_close_tab(browser_connection):
    """Test opening Google in a tab and closing it."""
    browser = browser_connection
    
    # Get existing contexts (browser should already be running)
    contexts = browser.contexts
    assert len(contexts) > 0, "Browser should have at least one context"
    
    # Use the first available context
    context = contexts[0]
    
    # Create a new page/tab
    page = context.new_page()
    
    try:
        # Navigate to Google
        page.goto("https://www.google.com", wait_until="networkidle")
        
        # Verify we're on Google
        assert "google" in page.url.lower(), f"Expected Google URL, got {page.url}"
        assert page.title(), "Page should have a title"
        
        print(f"✓ Successfully opened Google: {page.url}")
        print(f"  Page title: {page.title()}")
        
    finally:
        # Close the tab
        page.close()
        print("✓ Tab closed successfully")

