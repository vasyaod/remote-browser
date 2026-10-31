#!/bin/bash
# Create directory for Chrome user data
SESSION_DATA_PATH=${SESSION_DATA_PATH:-/session-data}
mkdir -p "${SESSION_DATA_PATH}"

# Per-session proxy (remote-browser-service#104). With PROXY_ENABLED=1 the
# service hands the pod PROXY_URL (an http://user:pass@host:port credential),
# and Chromium must never browse without it: no PROXY_URL means no browser.
# PROXY_URL stays a plain shell variable from here on, so no child process
# inherits it except the forwarder, which gets it in its own environment
# (never argv, which `ps` shows). Never echo it.
if [ "${PROXY_ENABLED:-0}" = "1" ]; then
  if [ -z "$PROXY_URL" ]; then
    echo "PROXY_ENABLED=1 but PROXY_URL is empty: refusing to start Chromium unproxied"
    exit 1
  fi
  export -n PROXY_URL
fi

# Start Xvfb in the background with configurable resolution
RESOLUTION=${VNC_RESOLUTION:-1920x1080x24}
# -noreset: Xvfb otherwise restores its stock keymap whenever its last client
# disconnects, which would undo the keymap change below.
Xvfb :99 -screen 0 ${RESOLUTION} -noreset &
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

# x11vnc types a character the keymap lacks (Cyrillic, accented letters, ...) by
# mapping it onto a keycode that has no symbols, and the stock US keymap has only
# 18 of those: the 19th distinct such character in a session was silently dropped
# (remote-browser-service#74). So drop the XF86 media/launcher keys that nobody
# presses in a remote browser, which leaves x11vnc 72 spare keycodes.
#
# Keep the keycodes that are system keys to Chrome or fluxbox, though: Chrome
# reads a key by its keycode (evdev code + 8), not by the keysym x11vnc put on
# it, so a character typed on a freed BrowserBack/BrowserForward keycode is lost,
# one on BrowserRefresh reloads the page, and the volume/power/launcher/media
# ones fire their action as well. Fluxbox's default keys file grabs raw keycodes
# 160, 174 and 176 for amixer, which swallows the character (remote-browser#5).
# A reserved keycode keeps its XF86 binding, or gets VoidSymbol if it has none,
# so x11vnc never picks it (132, IntlYen, is one of the stock 18 spares). F13-F24,
# Lang5 (93), IntlRo (97) and the keycodes Chrome has no code for stay free.
RESERVED_KEYCODES="121 122 123 124 128 132 141 142 143 145 148 150 151 152 160 \
161 163 164 165 166 167 169 171 172 173 174 175 176 179 180 181 209 215 216 \
225 232 233 235 239 240 241"
if xkbcomp -xkb :99 /tmp/keymap.xkb 2>/dev/null \
    && RESERVED_KEYCODES="$RESERVED_KEYCODES" python3 - /tmp/keymap.xkb /tmp/keymap-free.xkb <<'PY' \
    && xkbcomp -w 0 /tmp/keymap-free.xkb :99 2>/dev/null; then
import os, re, sys
keymap = open(sys.argv[1]).read()
keycodes = keymap.split("xkb_keycodes", 1)[1].split("\n};", 1)[0]
code = {name: int(n) for name, n in re.findall(r"<([^>]+)>\s*=\s*(\d+);", keycodes)}
reserved = {int(n) for n in os.environ["RESERVED_KEYCODES"].split()}
bound = {code.get(name) for name in re.findall(r"^\s*key\s+<([^>]+)>", keymap, re.M)}
out = []
for line in keymap.splitlines(keepends=True):
    key = re.match(r"\s*key\s+<([^>]+)>\s*\{\s*\[\s*XF86", line)
    if key and code.get(key.group(1)) not in reserved:
        continue
    out.append(line)
    if re.match(r"\s*xkb_symbols\b", line):
        out += [f"    key <{name}> {{ [ VoidSymbol ] }};\n" for name, n in code.items()
                if n in reserved and n not in bound]
open(sys.argv[2], "w").write("".join(out))
PY
  echo "keymap: freed the XF86 keycodes for x11vnc, kept Chrome's system keycodes"
else
  echo "keymap: could not free the XF86 keycodes; x11vnc keeps 18 spare"
fi

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

# Start VNC server with password if provided.
#
# x11vnc runs under a small soft RLIMIT_NOFILE on purpose. libvncserver's
# rfbProcessNewConnection() counts open descriptors by calling fcntl() on every
# fd from 0 to the soft limit before it accepts a client (its fd-quota check,
# the CVE-2020-14405 fix). Container runtimes that hand pods a soft limit of
# ~1e9 (systemd's "infinity") turn that into minutes of CPU per connection:
# the port accepts, no "RFB 003.008" banner ever comes, every viewer sits at
# "Connecting...". x11vnc needs a handful of fds; 4096 keeps the loop at ~1 ms.
# X11VNC_EXTRA_ARGS lets an operator try x11vnc flags without rebuilding.
X11VNC_NOFILE=${X11VNC_NOFILE:-4096}
echo "nofile limits: soft=$(ulimit -Sn) hard=$(ulimit -Hn); x11vnc will use soft=${X11VNC_NOFILE}"
start_x11vnc() {
  if [ -n "$VNC_PASSWORD" ]; then
    echo "Setting up VNC password..."
    mkdir -p /tmp/.vnc
    x11vnc -storepasswd "$VNC_PASSWORD" /tmp/.vnc/passwd 2>/dev/null || true
    chmod 600 /tmp/.vnc/passwd
    ( ulimit -S -n "${X11VNC_NOFILE}" 2>/dev/null; exec x11vnc -display :99 -forever -shared -rfbauth /tmp/.vnc/passwd -rfbport 5900 ${X11VNC_EXTRA_ARGS} ) &
    echo $! > /tmp/x11vnc.pid
    echo "VNC server started with password authentication"
  else
    ( ulimit -S -n "${X11VNC_NOFILE}" 2>/dev/null; exec x11vnc -display :99 -forever -shared -nopw -rfbport 5900 ${X11VNC_EXTRA_ARGS} ) &
    echo $! > /tmp/x11vnc.pid
    echo "VNC server started without password"
  fi
}

# A VNC server that accepts TCP but never sends the "RFB 003.008" banner is a
# wedged x11vnc: the port looks open, every viewer sits at "Connecting...", and
# nothing in the pod says why. Probe the banner from inside and restart x11vnc
# when it stops answering, logging where the old process was stuck first.
vnc_responds() {
  timeout 8 bash -c '
    exec 3<>/dev/tcp/127.0.0.1/5900 || exit 1
    IFS= read -r -t 5 -n 12 banner <&3
    exec 3>&-
    [[ "$banner" == RFB* ]]
  ' 2>/dev/null
}

x11vnc_diag() {
  local pid
  pid=$(cat /tmp/x11vnc.pid 2>/dev/null)
  echo "[vnc-watchdog] x11vnc pid=${pid:-?}" \
    "state=$(grep -E '^State' "/proc/$pid/status" 2>/dev/null | tr -s '\t ' ' ')" \
    "wchan=$(cat "/proc/$pid/wchan" 2>/dev/null)" \
    "syscall=$(cut -d' ' -f1 "/proc/$pid/syscall" 2>/dev/null)" \
    "utime/stime=$(awk '{print $14"/"$15}' "/proc/$pid/stat" 2>/dev/null)" \
    "threads=$(ls "/proc/$pid/task" 2>/dev/null | wc -l)" \
    "fds=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l)"
  # Userspace backtrace (x11vnc is this subshell's child, so Yama ptrace_scope=1
  # allows it). Module load addresses let the trace be symbolised offline against
  # the Debian x11vnc-dbgsym / libvncserver1 packages.
  if command -v eu-stack >/dev/null 2>&1 && [ -n "$pid" ]; then
    grep -E 'r-xp.*(x11vnc|libvncserver|libX11|libc\.so)' "/proc/$pid/maps" 2>/dev/null | sed 's/^/[vnc-watchdog] map /'
    for i in 1 2 3; do
      echo "[vnc-watchdog] stack sample $i:"
      timeout 10 eu-stack -p "$pid" -m 2>&1 | sed 's/^/[vnc-watchdog]   /' | head -40
      sleep 1
    done
  fi
}

VNC_WATCHDOG_INTERVAL=${VNC_WATCHDOG_INTERVAL:-60}
(
  start_x11vnc
  sleep 5
  strikes=0
  while true; do
    if vnc_responds; then
      strikes=0
    else
      strikes=$((strikes + 1))
      echo "[vnc-watchdog] no RFB banner on 127.0.0.1:5900 (strike $strikes)"
      x11vnc_diag
      if [ "$strikes" -ge 2 ]; then
        echo "[vnc-watchdog] restarting x11vnc"
        kill -9 "$(cat /tmp/x11vnc.pid 2>/dev/null)" 2>/dev/null || true
        sleep 1
        start_x11vnc
        strikes=0
      fi
    fi
    sleep "$VNC_WATCHDOG_INTERVAL"
  done
) &
VNC_WATCHDOG_PID=$!

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

# With PROXY_ENABLED=1, Chromium reaches the network only through a local
# forwarder that adds the upstream's Proxy-Authorization (Chromium cannot take
# user:pass in --proxy-server). If the forwarder dies, Chromium points at a dead
# loopback port and every load fails with ERR_PROXY_CONNECTION_FAILED: that is
# the fail-closed behaviour. The watchdog below restarts it. No
# --proxy-bypass-list beyond Chromium's implicit loopback.
PROXY_FORWARDER_PORT=${PROXY_FORWARDER_PORT:-3128}
PROXY_FORWARDER_TIMEOUT=${PROXY_FORWARDER_TIMEOUT:-15}
PROXY_FLAGS=()
start_proxy_forwarder() {
  PROXY_URL="$PROXY_URL" PROXY_FORWARDER_PORT="$PROXY_FORWARDER_PORT" python3 /proxy_forwarder.py &
  echo $! > /tmp/proxy_forwarder.pid
}
proxy_forwarder_listening() {
  ( exec 3<>"/dev/tcp/127.0.0.1/${PROXY_FORWARDER_PORT}" ) 2>/dev/null
}
if [ "${PROXY_ENABLED:-0}" = "1" ]; then
  echo "PROXY_ENABLED=1 (country ${PROXY_COUNTRY:-?}): starting proxy forwarder on 127.0.0.1:${PROXY_FORWARDER_PORT}"
  start_proxy_forwarder
  for i in $(seq 1 $((PROXY_FORWARDER_TIMEOUT * 2))); do
    proxy_forwarder_listening && break
    kill -0 "$(cat /tmp/proxy_forwarder.pid)" 2>/dev/null || break
    sleep 0.5
  done
  if ! proxy_forwarder_listening; then
    echo "Proxy forwarder is not listening on 127.0.0.1:${PROXY_FORWARDER_PORT}: refusing to start Chromium unproxied"
    exit 1
  fi
  echo "Proxy forwarder is listening"
  PROXY_FLAGS=(
    --proxy-server="http://127.0.0.1:${PROXY_FORWARDER_PORT}"
    --force-webrtc-ip-handling-policy=disable_non_proxied_udp
    --webrtc-ip-handling-policy=disable_non_proxied_udp
    # Component updates and other background fetches would spend proxy bandwidth.
    --disable-background-networking
  )
  if [ -n "$BROWSER_LANG" ]; then
    PROXY_FLAGS+=(--lang="$BROWSER_LANG" --accept-lang="$BROWSER_LANG")
  fi
  # The browser's timezone and locale follow the exit country.
  export TZ LANG LANGUAGE
  if [ -n "$LANG" ]; then
    export LC_ALL="$LANG"
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
  /usr/local/bin/chrome --remote-debugging-port=${INTERNAL_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --remote-allow-origins=* --user-data-dir="${SESSION_DATA_PATH}" --disable-dev-shm-usage --start-maximized --window-size=1920,1080 --new-window about:blank --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --no-sandbox "${PROXY_FLAGS[@]}" ${EXTRA_BROWSER_PARAMS} 2>&1 &
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
  if [ "${PROXY_ENABLED:-0}" = "1" ] && ! kill -0 "$(cat /tmp/proxy_forwarder.pid 2>/dev/null)" 2>/dev/null; then
    echo "[proxy-watchdog] proxy forwarder died, restarting it"
    start_proxy_forwarder
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

