"""
Unit tests for proxy_forwarder.py against a fake authenticated upstream proxy.
No container needed.
"""
import base64
import os
import socket
import subprocess
import sys

import pytest

from .proxy_helpers import FakeUpstream, free_port, header_values, read_head, wait_listening

FORWARDER = os.path.join(os.path.dirname(__file__), "..", "proxy_forwarder.py")
SECRET = "s3cr3t-pa:ss@x"
SECRET_ENCODED = "s3cr3t-pa%3Ass%40x"


def start_forwarder(proxy_url, port):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PROXY_URL": proxy_url, "PROXY_FORWARDER_PORT": str(port)}
    return subprocess.Popen([sys.executable, FORWARDER], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@pytest.fixture
def upstream():
    up = FakeUpstream()
    yield up
    up.close()


@pytest.fixture
def forwarder(upstream):
    port = free_port()
    proc = start_forwarder(f"http://user%2B1:{SECRET_ENCODED}@127.0.0.1:{upstream.port}", port)
    assert wait_listening(port), "forwarder never listened"
    yield proc, port
    proc.kill()
    out = proc.communicate()[0].decode()
    assert SECRET not in out and SECRET_ENCODED not in out, "forwarder logged the credential"


def expected_auth():
    return b"Basic " + base64.b64encode(f"user+1:{SECRET}".encode())


def test_connect_adds_proxy_authorization_and_tunnels(upstream, forwarder):
    proc, port = forwarder
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
        head, _ = read_head(s)
        assert head.startswith(b"HTTP/1.1 200"), head
        s.sendall(b"tunnel bytes")
        assert s.recv(4096) == b"TUNNEL BYTES"
    up_head = upstream.heads[-1]
    assert up_head.startswith(b"CONNECT example.com:443 HTTP/1.1")
    assert header_values(up_head, "Proxy-Authorization") == [expected_auth()]
    # The credential is in the forwarder's environment only, never in its argv.
    assert SECRET_ENCODED.encode() not in open(f"/proc/{proc.pid}/cmdline", "rb").read()


def test_plain_http_adds_auth_strips_client_auth_and_closes(upstream, forwarder):
    _, port = forwarder
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n"
                  b"Proxy-Authorization: Basic Zm9vOmJhcg==\r\nProxy-Connection: keep-alive\r\n"
                  b"Connection: keep-alive\r\n\r\n")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    assert data.startswith(b"HTTP/1.1 200 OK") and data.endswith(b"hello from upstream")
    up_head = upstream.heads[-1]
    assert up_head.startswith(b"GET http://example.com/ HTTP/1.1")
    assert header_values(up_head, "Proxy-Authorization") == [expected_auth()]
    assert header_values(up_head, "Connection") == [b"close"]
    assert header_values(up_head, "Proxy-Connection") == []
    assert header_values(up_head, "Host") == [b"example.com"]


def test_upstream_407_becomes_502_not_an_auth_prompt():
    up = FakeUpstream(connect_status=b"407 Proxy Authentication Required")
    port = free_port()
    proc = start_forwarder(f"http://u:p@127.0.0.1:{up.port}", port)
    try:
        assert wait_listening(port)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
            head, _ = read_head(s)
        assert head.startswith(b"HTTP/1.1 502"), head
    finally:
        proc.kill()
        proc.wait()
        up.close()


def test_unreachable_upstream_is_502():
    dead = free_port()
    port = free_port()
    proc = start_forwarder(f"http://u:p@127.0.0.1:{dead}", port)
    try:
        assert wait_listening(port)
        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
            s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
            head, _ = read_head(s)
        assert head.startswith(b"HTTP/1.1 502"), head
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("url", ["", "https://u:p@host:443", "http://u:p@host", "http://u:p@host:notaport"])
def test_bad_proxy_url_exits_nonzero_without_echoing_it(url):
    proc = start_forwarder(url, free_port())
    out = proc.communicate(timeout=10)[0].decode()
    assert proc.returncode != 0
    assert "u:p" not in out and "notaport" not in out, out
