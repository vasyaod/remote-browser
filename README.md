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

## Build and Push

### Supported Architectures

- **ARM64** (aarch64/arm64) - for ARM-based systems like garage-2
- **x64** (amd64/x86_64) - for Intel/AMD systems

The Dockerfile automatically detects the architecture and installs the appropriate Chrome version.

### Using the build script (Recommended)

The build script supports both architectures:

```bash
chmod +x build.sh

# Build for ARM64 (default)
./build.sh [tag] [arm64]

# Build for x64
./build.sh [tag] x64

# Examples
./build.sh latest arm64    # Build ARM64 with tag 'latest'
./build.sh v1.0.0 x64      # Build x64 with tag 'v1.0.0'
./build.sh latest          # Build ARM64 with tag 'latest' (default)
```

### Manual Docker Build

#### For ARM64 (garage-2)

```bash
# Build the image
docker build --platform=linux/arm64 -t 192.168.100.1:5000/headless-brawser:latest .

# Login to registry
docker login 192.168.100.1:5000 -u registry

# Push to registry
docker push 192.168.100.1:5000/headless-brawser:latest
```

#### For x64 (Intel/AMD)

```bash
# Build the image
docker build --platform=linux/amd64 -t 192.168.100.1:5000/headless-brawser:latest .

# Login to registry
docker login 192.168.100.1:5000 -u registry

# Push to registry
docker push 192.168.100.1:5000/headless-brawser:latest
```

### Building on garage-2 directly

Since garage-2 is ARM64, you can build directly on the server:

```bash
# SSH to garage-2
ssh root@192.168.4.107

# Copy files to garage-2 (from your local machine)
scp -r garage-2/headless-brawser root@192.168.4.107:/tmp/

# On garage-2, build and push
cd /tmp/headless-brawser
docker build -t 192.168.100.1:5000/headless-brawser:latest .
docker login 192.168.100.1:5000 -u registry
docker push 192.168.100.1:5000/headless-brawser:latest
```

## Usage

### Run the container

```bash
docker run -d \
  --name headless-browser \
  -p 9222:9222 \
  -p 5900:5900 \
  192.168.100.1:5000/headless-brawser:latest
```

### Connect via VNC

Use any VNC client to connect to `localhost:5900` (no password required).

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

## Notes

- The container runs in headless mode with Xvfb
- VNC access allows visual debugging and monitoring
- Remote debugging port enables programmatic browser control
- User data directory persists browser state between restarts

