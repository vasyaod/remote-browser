#!/usr/bin/env python3
"""
Test script: Connect to remote browser via WebSocket debugger URL.

This script fetches the WebSocket debugger URL from the Chrome DevTools Protocol
endpoint and connects directly to it using Playwright.

Usage:
    # Default: connects to http://192.168.100.12:9222
    python test_websocket_connection.py

    # With authentication token
    DEVTOOLS_TOKEN=mytoken123 python test_websocket_connection.py

    # With custom CDP endpoint
    CDP_ENDPOINT=http://localhost:9222 python test_websocket_connection.py
"""
import os
import sys
import json
import requests
from playwright.sync_api import sync_playwright


def get_websocket_debugger_url(cdp_endpoint="http://192.168.100.12:9222", devtools_token=None):
    """
    Fetch WebSocket debugger URL from Chrome DevTools Protocol endpoint.
    
    Args:
        cdp_endpoint: The CDP endpoint URL (default: http://192.168.100.12:9222)
        devtools_token: Optional authentication token
        
    Returns:
        WebSocket debugger URL string
    """
    # Prepare authentication if token is provided
    auth = None
    if devtools_token:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth('token', devtools_token)
    
    # Fetch the list of available pages/targets
    json_url = f"{cdp_endpoint}/json"
    print(f"Fetching WebSocket debugger URL from {json_url}...")
    
    try:
        response = requests.get(json_url, auth=auth, timeout=5)
        response.raise_for_status()
        
        pages = response.json()
        if not pages:
            raise ValueError("No pages found in CDP response")
        
        # Get the first available page's WebSocket debugger URL
        # You can also filter by type or other criteria if needed
        websocket_url = pages[0].get("webSocketDebuggerUrl")
        
        if not websocket_url:
            raise ValueError("No webSocketDebuggerUrl found in CDP response")
        
        print(f"✓ Found WebSocket debugger URL: {websocket_url}")
        print(f"  Page title: {pages[0].get('title', 'N/A')}")
        print(f"  Page URL: {pages[0].get('url', 'N/A')}")
        
        return websocket_url
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching CDP endpoint: {e}")
        sys.exit(1)
    except (KeyError, ValueError) as e:
        print(f"✗ Error parsing CDP response: {e}")
        print(f"  Response: {response.text[:500]}")
        sys.exit(1)


def test_websocket_connection():
    """Test connecting via WebSocket debugger URL and opening Google."""
    # Get configuration from environment variables
    cdp_endpoint = os.environ.get("CDP_ENDPOINT", "http://192.168.100.12:9222")
    devtools_token = os.environ.get("DEVTOOLS_TOKEN")
    
    # Fetch WebSocket debugger URL
    websocket_url = get_websocket_debugger_url(cdp_endpoint, devtools_token)
    
    # Connect directly to the WebSocket debugger URL
    print(f"\nConnecting to browser via WebSocket URL...")
    print(f"  WebSocket URL: {websocket_url}")
    try:
        with sync_playwright() as p:
            # Connect directly to the WebSocket debugger URL
            # This connects to the specific page referenced by the WebSocket URL
            browser = p.chromium.connect_over_cdp(websocket_url)
            print(f"✓ Connected to browser via WebSocket URL")
            
            # Get existing contexts
            contexts = browser.contexts
            if not contexts:
                raise ValueError("No browser contexts found after connecting")
            
            context = contexts[0]
            print(f"✓ Using existing context")
            
            # Wait a moment for pages to be available
            import time
            time.sleep(1)
            
            # Try to get pages from context
            pages = context.pages
            if pages and len(pages) > 0:
                # Use the existing page from WebSocket connection
                page = pages[0]
                print(f"✓ Using existing page from WebSocket connection")
            else:
                # If no pages in context, try connecting via HTTP endpoint instead
                # to allow creating new pages
                print(f"  Note: WebSocket URL connects to specific page, using HTTP endpoint for new page creation")
                browser.close()
                browser = p.chromium.connect_over_cdp(cdp_endpoint)
                contexts = browser.contexts
                context = contexts[0]
                page = context.new_page()
                print(f"✓ Created new page")
            
            try:
                # Navigate to Google
                print(f"\nNavigating to Google...")
                page.goto("https://www.google.com", wait_until="networkidle")
                
                # Verify we're on Google
                assert "google" in page.url.lower(), f"Expected Google URL, got {page.url}"
                print(f"✓ Successfully opened Google: {page.url}")
                print(f"  Page title: {page.title()}")
                
            finally:
                # Close the tab
                page.close()
                print(f"\n✓ Tab closed successfully")
            
            # Note: We don't close the browser here because it's managed by the container
            # browser.close()
            
    except Exception as e:
        print(f"✗ Error during WebSocket connection: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 60)
    print("WebSocket Debugger URL Connection Test")
    print("=" * 60)
    
    try:
        test_websocket_connection()
        print("\n" + "=" * 60)
        print("✓ Test completed successfully!")
        print("=" * 60)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed: {e}")
        sys.exit(1)

