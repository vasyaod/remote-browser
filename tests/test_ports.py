"""
Tests for remote-browser container ports.

Tests that all required ports are accessible and responding correctly.
"""
import socket
import time
import os
import requests
import pytest
import subprocess
import re


@pytest.fixture(scope="module")
def container_name():
    """Container name for testing."""
    return "test-remote-browser"


@pytest.fixture(scope="module")
def wait_for_services():
    """Wait for services to start."""
    time.sleep(10)


def test_port_9222_chrome_devtools(container_name, wait_for_services):
    """Test that Chrome DevTools port 9222 is accessible."""
    max_attempts = 30
    attempt = 0
    
    # Get DevTools token from environment variable (optional)
    devtools_token = os.environ.get("DEVTOOLS_TOKEN")
    
    # Prepare auth if token is provided
    auth = None
    if devtools_token:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth('token', devtools_token)
    
    while attempt < max_attempts:
        try:
            response = requests.get("http://localhost:9222/json", timeout=2, auth=auth)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert len(response.json()) >= 0, "Response should be valid JSON"
            print(f"✓ Port 9222 is accessible")
            print(f"  Response preview: {response.text[:200]}")
            return
        except (requests.exceptions.RequestException, AssertionError) as e:
            attempt += 1
            if attempt >= max_attempts:
                pytest.fail(f"Port 9222 failed to respond after {max_attempts} attempts: {e}")
            time.sleep(2)


def test_port_5900_vnc_server(container_name, wait_for_services):
    """Test that VNC server port 5900 is accessible."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    try:
        result = sock.connect_ex(('localhost', 5900))
        assert result == 0, f"Port 5900 connection failed with code {result}"
        print("✓ Port 5900 is accessible")
    except Exception as e:
        pytest.fail(f"Port 5900 is not accessible: {e}")
    finally:
        sock.close()


def test_vnc_password_authentication(container_name, wait_for_services):
    """Test that VNC password authentication works."""
    test_password = "testpass123"
    
    # Check container logs for password setup confirmation
    logs_result = subprocess.run(
        ["docker", "logs", container_name],
        capture_output=True, text=True
    )
    logs = logs_result.stdout
    assert "VNC server started with password authentication" in logs, \
        "VNC password should be configured"
    print("✓ VNC password authentication configured in container")
    
    # Test VNC connection - verify port is accessible and requires authentication
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    
    try:
        result = sock.connect_ex(('localhost', 5900))
        assert result == 0, f"Port 5900 connection failed with code {result}"
        
        # Read VNC protocol handshake
        data = sock.recv(12)
        assert len(data) >= 12, "VNC server should send protocol version"
        assert data.startswith(b"RFB"), "Should receive RFB protocol header"
        print(f"✓ VNC server responded with protocol: {data[:12].decode('ascii', errors='ignore')}")
        
        # Send client version
        sock.send(b"RFB 003.008\n")
        
        # Read number of security types (1 byte)
        num_sec_types_data = sock.recv(1)
        assert len(num_sec_types_data) == 1, "Should receive number of security types"
        num_sec_types = num_sec_types_data[0]
        print(f"✓ VNC server offers {num_sec_types} security type(s)")
        assert num_sec_types > 0, "VNC server should offer security types"
        
        # Read security types (N bytes where N is num_sec_types)
        sec_types = sock.recv(num_sec_types)
        assert len(sec_types) == num_sec_types, f"Should receive {num_sec_types} security type bytes"
        # Security type 2 is VNC authentication
        assert b'\x02' in sec_types, "VNC authentication (type 2) should be available"
        print("✓ VNC authentication (password) is available")
        
        print(f"✓ VNC password authentication test passed (password: {test_password})")
        
    except Exception as e:
        pytest.fail(f"VNC password authentication test failed: {e}")
    finally:
        sock.close()



def test_x11vnc_runs_under_a_small_nofile_limit(container_name, wait_for_services):
    """start.sh must start x11vnc with a small soft RLIMIT_NOFILE.

    libvncserver's rfbProcessNewConnection() fcntl()s every fd from 0 to the soft
    limit before accepting a client; with the ~1e9 limit production pods inherit
    that is minutes per connection and VNC hangs at "Connecting...". The hosted
    runner's dockerd can't grant such a limit, so pin the mechanism instead:
    the running x11vnc's soft limit is the capped one, not the inherited one.
    """
    pid = subprocess.run(
        ["docker", "exec", container_name, "cat", "/tmp/x11vnc.pid"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert pid.isdigit(), f"x11vnc pid file missing/odd: {pid!r}"
    limits = subprocess.run(
        ["docker", "exec", container_name, "cat", f"/proc/{pid}/limits"],
        capture_output=True, text=True, check=True,
    ).stdout
    line = next(l for l in limits.splitlines() if l.startswith("Max open files"))
    soft = int(line.split()[3])
    print(f"x11vnc pid {pid} nofile: {line}")
    assert soft <= 4096, f"x11vnc soft nofile should be capped (got {soft})"
    cmd = subprocess.run(
        ["docker", "exec", container_name, "cat", f"/proc/{pid}/cmdline"],
        capture_output=True, text=True, check=True,
    ).stdout.replace("\0", " ")
    assert cmd.startswith("x11vnc"), f"pid file does not point at x11vnc: {cmd!r}"


def test_keymap_leaves_x11vnc_spare_keycodes(container_name, wait_for_services):
    """start.sh must free the XF86 keycodes so x11vnc can type non-ASCII text.

    x11vnc types a character the keymap lacks (Cyrillic, accented Latin, ...) by
    binding it to a keycode with no symbols and never reuses a bound one. The
    stock Xvfb US keymap has only 18 such keycodes, so the 19th distinct
    non-ASCII character of a session was silently dropped
    (remote-browser-service#74). Count the empty keycodes of the live keymap,
    and check that the keycodes Chrome or fluxbox treat as system keys (volume,
    power, BrowserBack, BrowserRefresh, ...) stayed bound, so x11vnc never picks
    them (remote-browser#5).
    """
    logs = subprocess.run(
        ["docker", "logs", container_name],
        capture_output=True, text=True,
    ).stdout
    assert "keymap: freed the XF86 keycodes for x11vnc, kept Chrome's system keycodes" in logs, \
        "start.sh should log that it freed the XF86 keycodes"
    keymap = subprocess.run(
        ["docker", "exec", container_name, "xkbcomp", "-xkb", ":99", "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    keycodes = keymap.split("xkb_keycodes", 1)[1].split("};", 1)[0]
    lo = int(re.search(r"minimum\s*=\s*(\d+);", keycodes).group(1))
    hi = int(re.search(r"maximum\s*=\s*(\d+);", keycodes).group(1))
    code = {name: int(n) for name, n in re.findall(r"<([^>]+)>\s*=\s*(\d+);", keycodes)}
    symbols = keymap.split("xkb_symbols", 1)[1]
    names = re.findall(r"^\s*key\s+<([^>]+)>\s*\{", symbols, re.M)
    # This also counts keycode 8, which has no name and which x11vnc does not
    # use, so the stock keymap comes out at 19 here and the patched one at 73.
    spare = (hi - lo + 1) - len(names)
    print(f"keycodes {lo}..{hi}, {len(names)} with symbols, {spare} spare")
    assert spare >= len(set(NON_ASCII_TEXT) - {" "}), \
        f"x11vnc needs a spare keycode per distinct non-ASCII character (got {spare}; stock is 19)"
    # Volume, power, IntlYen, Open, Paste, the amixer keys fluxbox grabs, Back,
    # Forward and Reload: a character typed on one of these is lost or reloads.
    reserved = {122, 123, 124, 132, 142, 143, 160, 161, 164, 165, 166, 167, 174, 176, 181}
    unbound = sorted(reserved - {code.get(name) for name in names})
    assert not unbound, f"system keycodes left spare for x11vnc: {unbound}"


# 70 distinct characters the US keymap lacks, so x11vnc has to bind every one of
# them to a spare keycode, almost all 72 of them: the Russian pangram (all 33
# letters), the Greek alphabet and accented Latin.
NON_ASCII_TEXT = (
    "съешь же ещё этих мягких французских булок да выпей чаю "
    "αβγδεζηθικλμνξοπρστυφχψω "
    "ąćęłńśźżčďěňř"
)

# DOM `code`s of keys Chrome or the desktop act on. A typed character must not
# arrive on one of these: the volume, power and lock keys swallow it, BrowserBack
# and BrowserRefresh navigate away (remote-browser#5).
SYSTEM_KEY_CODES = re.compile(
    r"^(Audio|Browser|Launch|Media|Brightness|Mail|Display|Power|Sleep|WakeUp|"
    r"Eject|Open|Paste|Copy|Cut|Find|Undo|Again|Select|Props|Help|"
    r"ShowAllWindows|ContextMenu)"
)


class _VncKeyboard:
    """The few RFB 3.8 messages needed to send keys, as RBS `type` does."""

    def __init__(self, host, port, password):
        self.sock = socket.create_connection((host, port), timeout=10)
        version = self._read(12)
        assert version.startswith(b"RFB "), f"not a VNC server: {version!r}"
        self.sock.sendall(b"RFB 003.008\n")
        types = self._read(self._read(1)[0])
        if 2 in types and password:
            from Crypto.Cipher import DES
            self.sock.sendall(b"\x02")
            # VNC authentication: DES with the bit order of each key byte reversed.
            key = bytes(int(f"{b:08b}"[::-1], 2) for b in password.encode()[:8].ljust(8, b"\0"))
            self.sock.sendall(DES.new(key, DES.MODE_ECB).encrypt(self._read(16)))
        else:
            assert 1 in types, f"server wants a password (security types {list(types)})"
            self.sock.sendall(b"\x01")
        assert self._read(4) == b"\0\0\0\0", "VNC authentication failed"
        self.sock.sendall(b"\x01")  # ClientInit: shared
        self._read(20)
        self._read(int.from_bytes(self._read(4), "big"))

    def _read(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            assert chunk, "VNC server closed the connection"
            data += chunk
        return data

    def key(self, keysym, down):
        self.sock.sendall(bytes([4, int(down), 0, 0]) + keysym.to_bytes(4, "big"))

    def close(self):
        self.sock.close()


def _keysym(char):
    cp = ord(char)
    return cp if cp <= 0xFF else 0x01000000 + cp


def test_vnc_types_non_ascii_text_into_chrome(wait_for_services):
    """Type 70 distinct non-ASCII characters through VNC into a Chrome textarea.

    x11vnc binds each one to a spare keycode, and Chrome reads a key by its
    keycode, not by its keysym. So a spare keycode that Chrome knows as volume,
    power, BrowserBack or BrowserRefresh loses the character or reloads the page
    (remote-browser#5). The keymap test above only counts spare keycodes; this
    one checks what Chrome actually receives. It types the way RBS `type` does
    (remote-browser-service server/api/vnc.py): release every new keysym first so
    x11vnc binds it, wait for Chrome to see the new mapping, then press each key.
    """
    assert len(set(NON_ASCII_TEXT) - {" "}) == 70
    devtools_token = os.environ.get("DEVTOOLS_TOKEN")
    cdp_url = (f"http://token:{devtools_token}@localhost:9222" if devtools_token
               else "http://localhost:9222")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        page = browser.contexts[0].pages[0]
        page.bring_to_front()
        page.set_content(
            "<textarea id=t style='position:fixed;inset:0;width:100%;height:100%'></textarea>"
            "<script>window.codes = []; document.addEventListener('keydown',"
            " e => window.codes.push([e.key, e.code]), true);</script>")
        page.focus("#t")
        page.evaluate("window.marker = 1")
        vnc = _VncKeyboard("localhost", 5900, os.environ.get("VNC_PASSWORD", "testpass123"))
        try:
            for chunk in (NON_ASCII_TEXT[i:i + 20] for i in range(0, len(NON_ASCII_TEXT), 20)):
                for char in chunk:
                    vnc.key(_keysym(char), False)
                time.sleep(0.5)
                for char in chunk:
                    vnc.key(_keysym(char), True)
                    vnc.key(_keysym(char), False)
                    time.sleep(0.02)
            time.sleep(1)
        finally:
            vnc.close()
        assert page.evaluate("window.marker") == 1, "a typed character reloaded the page"
        value = page.evaluate("document.getElementById('t').value")
        codes = page.evaluate("window.codes")
        browser.close()
    lost = sorted(set(NON_ASCII_TEXT) - set(value))
    system = sorted({code for key, code in codes if SYSTEM_KEY_CODES.match(code)})
    print(f"typed {len(value)}/{len(NON_ASCII_TEXT)} characters; lost {''.join(lost)!r}")
    assert value == NON_ASCII_TEXT, f"lost {len(lost)} characters: {''.join(lost)!r}"
    assert not system, f"typed characters arrived as system keys: {system}"
