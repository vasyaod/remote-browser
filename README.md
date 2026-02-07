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

## Chromium Parameters

The container runs Chromium with:
- `--remote-debugging-port=9222`: Enables Chrome DevTools Protocol
- `--user-data-dir="/session-data"`: Persistent user data directory
- `--no-sandbox`: Required for running in containers
- `--disable-dev-shm-usage`: Prevents shared memory issues

## Environment Variables

- `VNC_PASSWORD`: Set a password for VNC access (optional)
- `VNC_RESOLUTION`: Set the display resolution (default: `1920x1080x24`)
- `SESSION_DATA_PATH`: Set the path for Chrome user data directory (default: `/session-data`)

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
