#!/bin/bash
# Create directory for Chrome user data
SESSION_DATA_PATH=${SESSION_DATA_PATH:-/session-data}
mkdir -p "${SESSION_DATA_PATH}"

# Start Xvfb in the background with configurable resolution
RESOLUTION=${VNC_RESOLUTION:-1920x1080x24}
Xvfb :99 -screen 0 ${RESOLUTION} &
export DISPLAY=:99

# Wait for Xvfb to be ready before starting VNC
for i in {1..30}; do
  if xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "Xvfb is ready"
    break
  fi
  echo "Waiting for Xvfb... ($i/30)"
  sleep 1
done

# Start fluxbox window manager
fluxbox &
sleep 2

# Start VNC server with password if provided
if [ -n "$VNC_PASSWORD" ]; then
  echo "Setting up VNC password..."
  mkdir -p /tmp/.vnc
  x11vnc -storepasswd "$VNC_PASSWORD" /tmp/.vnc/passwd 2>/dev/null || true
  chmod 600 /tmp/.vnc/passwd
  x11vnc -display :99 -forever -shared -rfbauth /tmp/.vnc/passwd -rfbport 5900 &
  echo "VNC server started with password authentication"
else
  x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
  echo "VNC server started without password"
fi

sleep 1

# Start Chrome/Chromium with remote debugging on loopback-only internal port
INTERNAL_DEBUG_PORT=9223
EXTERNAL_DEBUG_PORT=9222

# Function to start Chromium
start_chromium() {
  # Ensure DISPLAY is set
  export DISPLAY=:99
  # Wait for X server to be ready
  if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "X server not ready, waiting..."
    sleep 2
  fi
  # Launch Chromium maximized to fill the screen
  # Flags to prevent browser from closing when all tabs are closed:
  # --new-window about:blank ensures there's always a window open
  # --disable-background-timer-throttling prevents background throttling
  # --disable-backgrounding-occluded-windows prevents window backgrounding
  # --disable-renderer-backgrounding prevents renderer backgrounding
  /usr/local/bin/chrome --remote-debugging-port=${INTERNAL_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --remote-allow-origins=* --user-data-dir="${SESSION_DATA_PATH}" --no-sandbox --disable-dev-shm-usage --start-maximized --window-size=1920,1080 --new-window about:blank --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding 2>&1 &
  CHROMIUM_PID=$!
  echo $CHROMIUM_PID > /tmp/chromium.pid
  echo "Chromium started with PID: $CHROMIUM_PID"
}

# Start Chromium
start_chromium

# Expose DevTools externally via TCP forwarder (9222 -> 127.0.0.1:9223)
socat TCP-LISTEN:${EXTERNAL_DEBUG_PORT},fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:${INTERNAL_DEBUG_PORT} &

# Monitor Chromium and restart if it exits
while true; do
  if [ -f /tmp/chromium.pid ]; then
    CHROMIUM_PID=$(cat /tmp/chromium.pid)
    if ! kill -0 $CHROMIUM_PID 2>/dev/null; then
      echo "Chromium process died, restarting..."
      sleep 2
      start_chromium
    fi
  else
    echo "Chromium PID file not found, starting Chromium..."
    start_chromium
  fi
  sleep 5
done &
MONITOR_PID=$!

# Keep container running
wait

