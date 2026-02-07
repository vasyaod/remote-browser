# Headless Browser (Chromium)

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
  --name headless-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  <docker-hub-username>/headless-browser:latest
```

### Connect via VNC

Use any VNC client to connect to `localhost:5900` (no password required by default).

You can set a VNC password using the `VNC_PASSWORD` environment variable:

```bash
docker run -d \
  --name headless-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  -e VNC_PASSWORD=yourpassword \
  <docker-hub-username>/headless-browser:latest
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
- `--user-data-dir="/chrome-data"`: Persistent user data directory
- `--no-sandbox`: Required for running in containers
- `--disable-dev-shm-usage`: Prevents shared memory issues

## Environment Variables

- `VNC_PASSWORD`: Set a password for VNC access (optional)
- `VNC_RESOLUTION`: Set the display resolution (default: `1920x1080x24`)

## Notes

- The container runs in headless mode with Xvfb
- VNC access allows visual debugging and monitoring
- Remote debugging port enables programmatic browser control
- User data directory persists browser state between restarts
