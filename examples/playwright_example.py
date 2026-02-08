#!/usr/bin/env python3
"""
Example: Using Playwright with remote-browser

This example demonstrates how to connect to the remote browser container
using Playwright via Chrome DevTools Protocol (CDP).

Prerequisites:
    pip install playwright

Usage:
    # Without authentication
    python playwright_example.py

    # With authentication token
    DEVTOOLS_TOKEN=mytoken123 python playwright_example.py
"""
import os
from playwright.sync_api import sync_playwright


def connect_to_remote_browser(use_auth=False):
    """Connect to remote browser with optional authentication."""
    with sync_playwright() as p:
        # Build CDP URL
        if use_auth:
            devtools_token = os.environ.get("DEVTOOLS_TOKEN", "mytoken123")
            cdp_url = f"http://token:{devtools_token}@localhost:9222"
            print(f"Connecting with authentication...")
        else:
            cdp_url = "http://localhost:9222"
            print(f"Connecting without authentication...")
        
        # Connect to the remote browser
        browser = p.chromium.connect_over_cdp(cdp_url)
        print(f"✓ Connected to remote browser")
        
        # Get existing contexts or create a new one
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            print(f"✓ Using existing context")
        else:
            context = browser.new_context()
            print(f"✓ Created new context")
        
        # Create a new page/tab
        page = context.new_page()
        print(f"✓ Created new page")
        
        # Example: Navigate to a website
        print(f"\nNavigating to Google...")
        page.goto("https://www.google.com", wait_until="networkidle")
        print(f"✓ Page loaded: {page.url}")
        print(f"  Title: {page.title()}")
        
        # Example: Take a screenshot
        screenshot_path = "/tmp/google_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"✓ Screenshot saved to {screenshot_path}")
        
        # Example: Get page content
        search_box = page.locator('textarea[name="q"]')
        if search_box.count() > 0:
            print(f"✓ Found search box")
            search_box.fill("Playwright automation")
            print(f"✓ Filled search box")
        
        # Example: Wait a bit to see the result
        page.wait_for_timeout(2000)
        
        # Close page
        page.close()
        print(f"\n✓ Page closed")
        
        # Note: We don't close the browser here because it's managed by the container
        # browser.close()


if __name__ == "__main__":
    # Check if authentication token is set
    use_auth = bool(os.environ.get("DEVTOOLS_TOKEN"))
    
    try:
        connect_to_remote_browser(use_auth=use_auth)
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure the remote-browser container is running:")
        print("  docker run -d --name remote-browser -p 9222:9222 -p 5900:5900 vasiliiv/remote-browser:latest")
        if use_auth:
            print("\nAnd if using authentication, make sure DEVTOOLS_TOKEN matches the container's token")

