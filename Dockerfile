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

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose ports
# 9222: Chrome remote debugging
# 5900: VNC server
EXPOSE 9222 5900

# Set environment variables
ENV DISPLAY=:99
ENV VNC_RESOLUTION=1920x1080x24
ENV SESSION_DATA_PATH=/session-data

# Use startup script
CMD ["/start.sh"]