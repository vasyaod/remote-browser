"""
start.sh proxy wiring, run for real with X/VNC/Chromium replaced by stubs.

The Chromium stub records its argv and the locale/proxy env it was given, so
these tests pin (a) the launch command is unchanged with PROXY_ENABLED unset,
(b) the proxy flags, locale env and a working forwarder with PROXY_ENABLED=1,
(c) the fail-closed exits, and (d) the credential never reaches argv or the log.
No container needed.
"""
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

from .proxy_helpers import FakeUpstream, free_port, header_values, read_head, wait_listening

REPO = Path(__file__).resolve().parent.parent
SECRET = "s3cr3t-pass"

# The Chromium launch command as it is with PROXY_ENABLED unset (start.sh
# start_chromium(); EXTRA_BROWSER_PARAMS empty).
def base_argv(session_data):
    return [
        "--remote-debugging-port=9223", "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*", f"--user-data-dir={session_data}",
        "--disable-dev-shm-usage", "--start-maximized", "--window-size=1920,1080",
        "--new-window", "about:blank", "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
        "--no-sandbox",
    ]


STUB_SLEEP = "#!/bin/sh\nexec sleep 600\n"
CHROME_STUB = """#!/bin/bash
printf '%s\\0' "$@" > "{dir}/chrome.argv.tmp"
printf 'TZ=%s\\nLANG=%s\\nLANGUAGE=%s\\nLC_ALL=%s\\nPROXY_URL=%s\\n' \
  "${{TZ-<unset>}}" "${{LANG-<unset>}}" "${{LANGUAGE-<unset>}}" "${{LC_ALL-<unset>}}" \
  "${{PROXY_URL+<set>}}" > "{dir}/chrome.env"
mv "{dir}/chrome.argv.tmp" "{dir}/chrome.argv"
exec sleep 600
"""


class Harness:
    def __init__(self, tmp_path, env):
        self.dir = tmp_path
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name, body in {"Xvfb": STUB_SLEEP, "fluxbox": STUB_SLEEP, "x11vnc": STUB_SLEEP,
                           "socat": STUB_SLEEP, "xdpyinfo": "#!/bin/sh\nexit 0\n",
                           "xkbcomp": "#!/bin/sh\nexit 1\n"}.items():
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod(0o755)
        chrome = tmp_path / "chrome"
        chrome.write_text(CHROME_STUB.format(dir=tmp_path))
        chrome.chmod(0o755)
        agent = tmp_path / "profile_agent.py"
        agent.write_text("import time\ntime.sleep(600)\n")
        (tmp_path / "home").mkdir()
        self.session_data = tmp_path / "session-data"

        script = (REPO / "start.sh").read_text()
        script = script.replace("/tmp/", f"{tmp_path}/")
        script = script.replace("/usr/local/bin/chrome", str(chrome))
        script = script.replace("/profile_agent.py", str(agent))
        script = script.replace("/proxy_forwarder.py", str(REPO / "proxy_forwarder.py"))
        (tmp_path / "start.sh").write_text(script)

        self.log = tmp_path / "container.log"
        full_env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
                    "SESSION_DATA_PATH": str(self.session_data),
                    "VNC_WATCHDOG_INTERVAL": "600"}
        full_env.update(env)
        with open(self.log, "wb") as log:
            self.proc = subprocess.Popen(["bash", str(tmp_path / "start.sh")], env=full_env,
                                         stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)

    def wait_chrome(self, timeout=30):
        argv = self.dir / "chrome.argv"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if argv.exists():
                return argv.read_bytes().split(b"\0")[:-1]
            if self.proc.poll() is not None:
                pytest.fail(f"start.sh exited {self.proc.returncode}: {self.log.read_text()}")
            time.sleep(0.2)
        pytest.fail("Chromium was never launched")

    def chrome_env(self):
        return dict(line.split("=", 1) for line in (self.dir / "chrome.env").read_text().splitlines())

    def group_cmdlines(self):
        out = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                if os.getpgid(int(pid)) == self.proc.pid:
                    out.append(open(f"/proc/{pid}/cmdline", "rb").read())
            except (OSError, ProcessLookupError):
                pass
        return out

    def stop(self):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait()


@pytest.fixture
def harness(tmp_path):
    started = []

    def start(**env):
        h = Harness(tmp_path, env)
        started.append(h)
        return h

    yield start
    for h in started:
        h.stop()


PROXY_ENV = {"PROXY_ENABLED": "1", "PROXY_COUNTRY": "de", "TZ": "Europe/Berlin",
             "LANG": "de_DE.UTF-8", "LANGUAGE": "de_DE:de", "BROWSER_LANG": "de-DE"}


def test_proxy_disabled_launch_command_is_unchanged(harness):
    h = harness()
    argv = h.wait_chrome()
    assert argv == [a.encode() for a in base_argv(h.session_data)]
    env = h.chrome_env()
    assert env["LC_ALL"] == "<unset>" and env["TZ"] == "<unset>"
    assert "forwarder" not in h.log.read_text().lower()


def test_proxy_enabled_wires_forwarder_flags_and_locale(harness):
    up = FakeUpstream()
    port = free_port()
    h = harness(PROXY_URL=f"http://user:{SECRET}@127.0.0.1:{up.port}",
                PROXY_FORWARDER_PORT=str(port), **PROXY_ENV)
    try:
        argv = h.wait_chrome()
        assert argv == [a.encode() for a in base_argv(h.session_data) + [
            f"--proxy-server=http://127.0.0.1:{port}",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--disable-background-networking",
            "--lang=de-DE", "--accept-lang=de-DE",
        ]]
        assert not any(a.startswith(b"--proxy-bypass-list") for a in argv)
        assert h.chrome_env() == {"TZ": "Europe/Berlin", "LANG": "de_DE.UTF-8",
                                  "LANGUAGE": "de_DE:de", "LC_ALL": "de_DE.UTF-8",
                                  "PROXY_URL": ""}

        # The forwarder Chromium points at reaches the upstream with credentials.
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
            assert read_head(s)[0].startswith(b"HTTP/1.1 200")
        assert header_values(up.heads[-1], "Proxy-Authorization")

        # ps never shows the credential.
        assert not any(SECRET.encode() in c for c in h.group_cmdlines())

        # Forwarder killed: the port is dead (loads fail), then the watchdog restarts it.
        fwd_pid = int((h.dir / "proxy_forwarder.pid").read_text())
        os.kill(fwd_pid, signal.SIGKILL)
        time.sleep(0.3)
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        assert wait_listening(port, timeout=15), "watchdog did not restart the forwarder"
        assert "proxy forwarder died, restarting" in h.log.read_text()
        assert SECRET not in h.log.read_text()
    finally:
        up.close()


def test_proxy_enabled_without_url_exits_before_chromium(harness):
    h = harness(**PROXY_ENV)
    assert h.proc.wait(timeout=10) != 0
    assert not (h.dir / "chrome.argv").exists()


def test_proxy_enabled_with_unusable_url_exits_before_chromium(harness):
    h = harness(PROXY_URL=f"https://user:{SECRET}@127.0.0.1:1", PROXY_FORWARDER_PORT=str(free_port()),
                **PROXY_ENV)
    assert h.proc.wait(timeout=30) != 0
    assert not (h.dir / "chrome.argv").exists()
    log = h.log.read_text()
    assert "refusing to start Chromium unproxied" in log
    assert SECRET not in log
