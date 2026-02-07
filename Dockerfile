FROM debian:bookworm-slim

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Chromium (NO snap on Debian), VNC, and X11 bits.
# We intentionally use Debian because Ubuntu's `chromium-browser` is a snap wrapper.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    x11vnc \
    fluxbox \
    curl \
    socat \
    ca-certificates \
    fonts-liberation \
    fonts-dejavu \
    xdg-utils \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libu2f-udev \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/chromium /usr/local/bin/chrome

# Create directory for Chrome user data
RUN mkdir -p /chrome-data

# Create startup script
RUN echo '#!/bin/bash\n\
# Start Xvfb in the background with configurable resolution\n\
RESOLUTION=${VNC_RESOLUTION:-1920x1080x24}\n\
Xvfb :99 -screen 0 ${RESOLUTION} &\n\
export DISPLAY=:99\n\
\n\
# Wait for Xvfb to be ready before starting VNC\n\
for i in {1..30}; do\n\
  if xdpyinfo -display :99 >/dev/null 2>&1; then\n\
    echo "Xvfb is ready"\n\
    break\n\
  fi\n\
  echo "Waiting for Xvfb... ($i/30)"\n\
  sleep 1\n\
done\n\
\n\
# Start fluxbox window manager\n\
fluxbox &\n\
sleep 2\n\
\n\
# Start VNC server with password if provided\n\
if [ -n "$VNC_PASSWORD" ]; then\n\
  echo "Setting up VNC password..."\n\
  mkdir -p /tmp/.vnc\n\
  x11vnc -storepasswd "$VNC_PASSWORD" /tmp/.vnc/passwd 2>/dev/null || true\n\
  chmod 600 /tmp/.vnc/passwd\n\
  x11vnc -display :99 -forever -shared -rfbauth /tmp/.vnc/passwd -rfbport 5900 &\n\
  echo "VNC server started with password authentication"\n\
else\n\
  x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &\n\
  echo "VNC server started without password"\n\
fi\n\
\n\
sleep 1\n\
\n\
# Start Chrome/Chromium with remote debugging on loopback-only internal port\n\
INTERNAL_DEBUG_PORT=9223\n\
EXTERNAL_DEBUG_PORT=9222\n\
\n\
# Function to start Chromium\n\
start_chromium() {\n\
  # Ensure DISPLAY is set\n\
  export DISPLAY=:99\n\
  # Wait for X server to be ready\n\
  if ! xdpyinfo -display :99 >/dev/null 2>&1; then\n\
    echo "X server not ready, waiting..."\n\
    sleep 2\n\
  fi\n\
  # Launch Chromium maximized to fill the screen\n\
  # Flags to prevent browser from closing when all tabs are closed:\n\
  # --new-window about:blank ensures there's always a window open\n\
  # --disable-background-timer-throttling prevents background throttling\n\
  # --disable-backgrounding-occluded-windows prevents window backgrounding\n\
  # --disable-renderer-backgrounding prevents renderer backgrounding\n\
  /usr/local/bin/chrome --remote-debugging-port=${INTERNAL_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --remote-allow-origins=* --user-data-dir="/chrome-data" --no-sandbox --disable-dev-shm-usage --start-maximized --window-size=1920,1080 --new-window about:blank --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding 2>&1 &\n\
  CHROMIUM_PID=$!\n\
  echo $CHROMIUM_PID > /tmp/chromium.pid\n\
  echo "Chromium started with PID: $CHROMIUM_PID"\n\
}\n\
\n\
# Start Chromium\n\
start_chromium\n\
\n\
# Expose DevTools externally via TCP forwarder (9222 -> 127.0.0.1:9223)\n\
socat TCP-LISTEN:${EXTERNAL_DEBUG_PORT},fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:${INTERNAL_DEBUG_PORT} &\n\
\n\
# Monitor Chromium and restart if it exits\n\
while true; do\n\
  if [ -f /tmp/chromium.pid ]; then\n\
    CHROMIUM_PID=$(cat /tmp/chromium.pid)\n\
    if ! kill -0 $CHROMIUM_PID 2>/dev/null; then\n\
      echo "Chromium process died, restarting..."\n\
      sleep 2\n\
      start_chromium\n\
    fi\n\
  else\n\
    echo "Chromium PID file not found, starting Chromium..."\n\
    start_chromium\n\
  fi\n\
  sleep 5\n\
done &\n\
MONITOR_PID=$!\n\
\n\
# Keep container running\n\
wait\n\
' > /start.sh && chmod +x /start.sh

# Expose ports
# 9222: Chrome remote debugging
# 5900: VNC server
EXPOSE 9222 5900

# Set environment variables
ENV DISPLAY=:99
ENV VNC_RESOLUTION=1920x1080x24

# Use startup script
CMD ["/start.sh"]