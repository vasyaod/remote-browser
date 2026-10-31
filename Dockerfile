FROM debian:bookworm-slim

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Chromium (NO snap on Debian), VNC, and X11 bits.
# We intentionally use Debian because Ubuntu's `chromium-browser` is a snap wrapper.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-sandbox \
    xvfb \
    x11vnc \
    fluxbox \
    curl \
    socat \
    elfutils \
    python3 \
    ca-certificates \
    tzdata \
    locales \
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

# Locales for the per-session proxy countries (remote-browser-service#104):
# start.sh sets LANG/LC_ALL for Chromium to the exit country's locale.
RUN printf '%s.UTF-8 UTF-8\n' en_US en_CA en_GB de_DE fr_FR nl_NL es_ES it_IT ru_RU uk_UA > /etc/locale.gen \
    && locale-gen

# Copy startup script and proxy
COPY start.sh /start.sh
COPY devtools_proxy.py /devtools_proxy.py
COPY profile_agent.py /profile_agent.py
COPY proxy_forwarder.py /proxy_forwarder.py
RUN chmod +x /start.sh /devtools_proxy.py /profile_agent.py /proxy_forwarder.py

# Create non-root user for Chromium (enables sandbox, no --no-sandbox needed)
RUN useradd -m -u 1000 -s /bin/bash browser \
    && mkdir -p /session-data \
    && chown -R browser:browser /session-data

# Run as non-root user
USER browser

# Expose ports
# 9222: Chrome remote debugging
# 5900: VNC server
# 9224: profile agent (orchestrator push/pull of the Chrome profile)
EXPOSE 9222 5900 9224

# Set environment variables
ENV DISPLAY=:99
ENV VNC_RESOLUTION=1920x1080x24
ENV SESSION_DATA_PATH=/session-data

# Use startup script
CMD ["/start.sh"]