# Remote Browser (Chromium) with VNC access

Docker container with headless Chromium browser, VNC access, and remote debugging capabilities.

## Features

- **Chromium Browser** with remote debugging on port 9222
- **VNC Server** on port 5900 for visual access
- **X11 Virtual Display** (Xvfb) for headless operation
- **Fluxbox** window manager

## Ports

- **9222**: Chrome remote debugging port
- **5900**: VNC server port

## Usage

### Run the container

```bash
docker run -d \
  --name remote-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  vasiliiv/remote-browser:latest
```

### Connect via VNC

Use any VNC client to connect to `localhost:5900` (no password required by default).

You can set a VNC password using the `VNC_PASSWORD` environment variable:

```bash
docker run -d \
  --name remote-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  -e VNC_PASSWORD=yourpassword \
  vasiliiv/remote-browser:latest
```

### Connect via Chrome DevTools

Open Chrome/Chromium and navigate to:
```
http://localhost:9222
```

Or use Chrome DevTools Protocol:
```bash
curl http://localhost:9222/json
```

You can set a token/password for Chrome DevTools port 9222 using the `DEVTOOLS_TOKEN` environment variable:

```bash
docker run -d \
  --name remote-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  -e DEVTOOLS_TOKEN=mytoken123 \
  vasiliiv/remote-browser:latest
```

When a token is set, access requires HTTP Basic Authentication:
```bash
# Using curl with Basic Auth
curl -u token:mytoken123 http://localhost:9222/json

# Or with empty username
curl -u :mytoken123 http://localhost:9222/json
```

### Connect via Playwright

You can control the browser programmatically using Playwright via Chrome DevTools Protocol:

**Without authentication:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # Connect to the remote browser
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    
    # Get existing context or create a new one
    contexts = browser.contexts
    if contexts:
        context = contexts[0]
    else:
        context = browser.new_context()
    
    # Create a new page
    page = context.new_page()
    
    # Navigate and interact
    page.goto("https://www.google.com")
    print(f"Page title: {page.title()}")
    
    # Close page and browser
    page.close()
    browser.close()
```

**With authentication token:**
```python
from playwright.sync_api import sync_playwright
import os

# Set token as environment variable or use directly
devtools_token = os.environ.get("DEVTOOLS_TOKEN", "mytoken123")

with sync_playwright() as p:
    # Connect with authentication
    cdp_url = f"http://token:{devtools_token}@localhost:9222"
    browser = p.chromium.connect_over_cdp(cdp_url)
    
    # Get existing context or create a new one
    contexts = browser.contexts
    if contexts:
        context = contexts[0]
    else:
        context = browser.new_context()
    
    # Create a new page
    page = context.new_page()
    
    # Navigate and interact
    page.goto("https://www.google.com")
    print(f"Page title: {page.title()}")
    
    # Close page and browser
    page.close()
    browser.close()
```

**Example: Taking a screenshot:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    page = context.new_page()
    
    page.goto("https://www.example.com")
    page.screenshot(path="screenshot.png")
    
    page.close()
    browser.close()
```

## Chromium Parameters

The container runs Chromium with:
- `--remote-debugging-port=9222`: Enables Chrome DevTools Protocol
- `--user-data-dir="/session-data"`: Persistent user data directory
- `--no-sandbox`: Required for running in containers
- `--disable-dev-shm-usage`: Prevents shared memory issues

## Environment Variables

- `VNC_PASSWORD`: Set a password for VNC access (optional)
- `DEVTOOLS_TOKEN`: Set a token/password for Chrome DevTools port 9222 (optional)
- `VNC_RESOLUTION`: Set the display resolution (default: `1920x1080x24`)
- `SESSION_DATA_PATH`: Set the path for Chrome user data directory (default: `/session-data`)

## Kubernetes Deployment

For Kubernetes deployment examples, see [Kubernetes Deployment Guide](docs/k8s.md).

## Notes

- The container runs in headless mode with Xvfb
- VNC access allows visual debugging and monitoring
- Remote debugging port enables programmatic browser control
- User data directory persists browser state between restarts

## License

Copyright (c) 2026

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
