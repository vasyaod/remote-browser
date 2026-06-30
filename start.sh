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

# Force every window to map maximized so a popup (e.g. OAuth/sign-in opened via
# window.open) overlays the main window full-screen instead of tiling beside it.
# This guarantees a single full-viewport window in the VNC view — never a split.
mkdir -p ~/.fluxbox
cat > ~/.fluxbox/apps <<'APPS'
[app] (name=.*)
  [Maximized] {yes}
  [Deco] {NONE}
  [Layer] {2}
[end]
APPS

# Start fluxbox window manager
fluxbox &
sleep 2
# Fluxbox may spawn a wallpaper warning popup via xmessage when no setter is
# installed; it can cover the fullscreen Chromium window and make kiosk mode
# appear broken.
pkill -x xmessage >/dev/null 2>&1 || true

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

# Start the profile agent so the orchestrator can push/pull the Chrome profile
# (plaintext tar.gz; the service owns S3 + encryption). Must be up before Chrome
# so a restore can land BEFORE Chrome opens the profile.
rm -f /tmp/profile_ready
echo "Starting profile agent..."
python3 /profile_agent.py &
PROFILE_AGENT_PID=$!

# When the orchestrator intends to restore a saved profile it sets PROFILE_RESTORE=1
# and PUTs the profile to the agent. Wait for the agent to extract it (it touches
# /tmp/profile_ready) before launching Chrome, so Chrome boots the restored profile.
# Legacy sessions leave PROFILE_RESTORE unset -> launch immediately (the service
# then restores via the older CDP path).
PROFILE_RESTORE_TIMEOUT=${PROFILE_RESTORE_TIMEOUT:-45}
if [ "${PROFILE_RESTORE:-0}" = "1" ]; then
  echo "PROFILE_RESTORE=1: waiting up to ${PROFILE_RESTORE_TIMEOUT}s for profile push..."
  for i in $(seq 1 "${PROFILE_RESTORE_TIMEOUT}"); do
    if [ -f /tmp/profile_ready ]; then
      echo "Profile restored after ${i}s; launching Chromium"
      break
    fi
    sleep 1
  done
  if [ ! -f /tmp/profile_ready ]; then
    echo "Profile not pushed within ${PROFILE_RESTORE_TIMEOUT}s; launching Chromium with empty profile"
  fi
fi

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
  /usr/local/bin/chrome --remote-debugging-port=${INTERNAL_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --remote-allow-origins=* --user-data-dir="${SESSION_DATA_PATH}" --disable-dev-shm-usage --start-maximized --window-size=1920,1080 --new-window about:blank --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --no-sandbox ${EXTRA_BROWSER_PARAMS} 2>&1 &
  CHROMIUM_PID=$!
  echo $CHROMIUM_PID > /tmp/chromium.pid
  echo "Chromium started with PID: $CHROMIUM_PID"
}

# Start Chromium
start_chromium

# Expose DevTools externally via HTTP proxy with optional authentication
if [ -n "$DEVTOOLS_TOKEN" ]; then
  echo "Starting DevTools proxy with authentication..."
  export INTERNAL_DEBUG_HOST=127.0.0.1
  export INTERNAL_DEBUG_PORT=${INTERNAL_DEBUG_PORT}
  export EXTERNAL_DEBUG_PORT=${EXTERNAL_DEBUG_PORT}
  python3 /devtools_proxy.py &
else
  echo "Starting DevTools proxy without authentication (using socat)..."
  # Fallback to socat if no token is set (backward compatible)
  socat TCP-LISTEN:${EXTERNAL_DEBUG_PORT},fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:${INTERNAL_DEBUG_PORT} &
fi

# Monitor Chromium and restart if it exits — UNLESS /tmp/no_restart is present,
# which the profile agent creates when it gracefully quiesces Chrome to take a
# consistent profile snapshot just before pod teardown. Respawning then would
# re-dirty the profile mid-tar, so honor the flag and leave Chrome down.
while true; do
  if [ -f /tmp/no_restart ]; then
    sleep 5
    continue
  fi
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

